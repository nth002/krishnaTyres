import jwt
from datetime import datetime, timedelta, timezone

from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from .storage import upload_image, upload_profile_image
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from decimal import Decimal, InvalidOperation
from django.db import transaction

# global API's

class BearerAuthentication(BaseAuthentication):

    def authenticate(self, request):

        auth_header = request.headers.get('Authorization')

        if not auth_header:
            raise AuthenticationFailed(
                "Authorization token is required"
            )

        if not auth_header.startswith('Bearer '):
            raise AuthenticationFailed(
                "Authorization header must use Bearer token"
            )

        token = auth_header.split(' ')[1]

        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed(
                "Token has expired"
            )

        except jwt.InvalidTokenError:
            raise AuthenticationFailed(
                "Invalid token"
            )

        u_id = payload.get('u_id')

        if not u_id:
            raise AuthenticationFailed(
                "Invalid token: user ID missing"
            )

        try:
            user = User.objects.select_related('role').get(
                u_id=u_id,
                is_active=True
            )
        except User.DoesNotExist:
            raise AuthenticationFailed(
                "User not found or inactive"
            )

        return (user, token)

def save_notification(receiver_u_id, message, title="Notification"):

    try:
        user = User.objects.get(
            u_id=receiver_u_id,
            is_active=True
        )
    except User.DoesNotExist:
        return False

    Notification.objects.create(
        receiver=user,
        title=title,
        message=message
    )

    return True

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_notifications(request):

    user = request.user

    notifications = Notification.objects.filter(
        receiver=user
    ).order_by('-created_at')

    data = []

    for notification in notifications:
        data.append({
            "notification_id": notification.notification_id,
            "title": notification.title,
            "message": notification.message,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
            "updated_at": notification.updated_at
        })

    return Response({
        "status": True,
        "message": "Notifications fetched successfully",
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['PUT'])
@authentication_classes([BearerAuthentication])
def mark_all_notifications_read(request):

    user = request.user

    updated_count = Notification.objects.filter(
        receiver=user,
        is_read=False
    ).update(
        is_read=True
    )

    return Response({
        "status": True,
        "message": "All notifications marked as read",
        "data": {
            "updated_count": updated_count
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT'])
@authentication_classes([BearerAuthentication])
def mark_notification_read(request, notification_id):

    user = request.user

    try:
        notification = Notification.objects.get(
            notification_id=notification_id,
            receiver=user
        )
    except Notification.DoesNotExist:
        return Response({
            "status": False,
            "message": "Notification not found"
        }, status=status.HTTP_404_NOT_FOUND)

    notification.is_read = True
    notification.save(
        update_fields=['is_read', 'updated_at']
    )

    return Response({
        "status": True,
        "message": "Notification marked as read",
        "data": {
            "notification_id": notification.notification_id,
            "is_read": notification.is_read
        }
    }, status=status.HTTP_200_OK)


# Master data fetching APIs for roles and categories, and user registration API.

@api_view(['GET'])
def get_roles(request):

    roles = Role.objects.filter(
        is_active=True
    ).order_by('role_name')

    data = []

    for role in roles:
        data.append({
            "role_id": role.role_id,
            "role_name": role.role_name,
            "role_code": role.role_code,
        })

    return Response({
        "status": True,
        "message": "Roles fetched successfully",
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_categories(request):

    categories = Category.objects.filter(
        is_active=True
    ).order_by('category_name')

    data = []

    for category in categories:
        data.append({
            "category_id": category.category_id,
            "category_name": category.category_name,
            "category_code": category.category_code,
            "description": category.description,
        })

    return Response({
        "status": True,
        "message": "Categories fetched successfully",
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_services(request):

    services = Service.objects.filter(
        is_active=True
    ).order_by('service_name')

    data = []

    for service in services:
        data.append({
            "service_id": service.service_id,
            "service_name": service.service_name,
            "service_price": service.service_price,
            "description": service.description,
        })

    return Response({
        "status": True,
        "message": "Services fetched successfully",
        "data": data
    }, status=status.HTTP_200_OK)

# crud and all other operations API's

@api_view(['POST'])
def register_user(request):

    name = request.data.get('name')
    number = request.data.get('number')
    role_id = request.data.get('role_id')
    subscribed = request.data.get('subscribed', False)
    mpin = request.data.get('mpin')
    profile_image_url = request.data.get('profile_image_url')

    # Required field validation
    if not name:
        return Response({
            "status": False,
            "message": "Name is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not number:
        return Response({
            "status": False,
            "message": "Mobile number is required"
        }, status=status.HTTP_400_BAD_REQUEST)


    if not role_id:
        return Response({
            "status": False,
            "message": "Role is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not mpin:
        return Response({
            "status": False,
            "message": "MPIN is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check duplicate mobile number
    if User.objects.filter(number=number).exists():
        return Response({
            "status": False,
            "message": "Mobile number already registered"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check role
    try:
        role = Role.objects.get(
            role_id=role_id,
            is_active=True
        )
    except Role.DoesNotExist:
        return Response({
            "status": False,
            "message": "Invalid or inactive role"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create user
    user = User.objects.create(
        name=name,
        number=number,
        role=role,
        subscribed=subscribed,
        mpin=mpin,
        profile_image_url=profile_image_url
    )

    return Response({
        "status": True,
        "message": "User registered successfully",
        "data": {
            "u_id": user.u_id,
            "name": user.name,
            "number": user.number,
            "role": {
                "role_id": role.role_id,
                "role_name": role.role_name,
                "role_code": role.role_code
            },
            "subscribed": user.subscribed,
            "profile_image_url": user.profile_image_url,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def login_user(request):

    number = request.data.get('number')
    mpin = request.data.get('mpin')
    role_id = request.data.get('role_id')

    if not number:
        return Response({
            "status": False,
            "message": "Mobile number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not mpin:
        return Response({
            "status": False,
            "message": "MPIN is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not role_id:
        return Response({
            "status": False,
            "message": "Role is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.select_related('role').get(
            number=number,
            role_id=role_id,
            is_active=True
        )
    except User.DoesNotExist:
        return Response({
            "status": False,
            "message": "Invalid mobile number or role"
        }, status=status.HTTP_401_UNAUTHORIZED)

    if user.mpin != mpin:
        return Response({
            "status": False,
            "message": "Invalid MPIN"
        }, status=status.HTTP_401_UNAUTHORIZED)

    # Token expiration: 24 hours
    expiration = datetime.now(timezone.utc) + timedelta(hours=24)

    payload = {
        "u_id": user.u_id,
        "role_id": user.role.role_id,
        "role_code": user.role.role_code,
        "exp": expiration,
        "iat": datetime.now(timezone.utc)
    }

    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )
  
    return Response({
        "status": True,
        "message": "Login successful",
        "data": {
            "u_id": user.u_id,
            "name": user.name,
            "number": user.number,

            "subscribed": user.subscribed,
            "profile_image_url": user.profile_image_url,
            "shop_open": user.shop_open,
            "emergency_service": user.emergency_service,
            "role": {
                "role_id": user.role.role_id,
                "role_name": user.role.role_name,
                "role_code": user.role.role_code
            },
            "access_token": token,
            "token_type": "Bearer",
            "expires_at": expiration
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def update_profile_image(request):
    user = request.user
    image = request.FILES.get('profile_image')

    if not image:
        return Response({
            "status": False,
            "message": "Profile image is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']

    if image.content_type not in allowed_types:
        return Response({
            "status": False,
            "message": "Only JPG, JPEG, PNG and WEBP images are allowed"
        }, status=status.HTTP_400_BAD_REQUEST)

    if image.size > 5 * 1024 * 1024:
        return Response({
            "status": False,
            "message": "Image size should not exceed 5 MB"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        image_url, file_name = upload_profile_image(image, user.u_id)

        user.profile_image_url = image_url
        user.save(update_fields=['profile_image_url', 'updated_at'])

        return Response({
            "status": True,
            "message": "Profile image updated successfully",
            "data": {
                "u_id": user.u_id,
                "profile_image_url": image_url
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print("SUPABASE ERROR:", repr(e))
        return Response({
            "status": False,
            "message": "Failed to upload profile image",
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def add_product(request):

    user = request.user
    product_name = request.data.get('product_name')
    product_price = request.data.get('product_price')
    stock_number = request.data.get('stock_number')
    category = request.data.get('category')
    brand_name = request.data.get('brand_name')
    vehicle_name = request.data.get('vehicle_name')
    description = request.data.get('description')

    product_image = request.FILES.get('product_image')

    if not product_name:
        return Response({
            "status": False,
            "message": "Product name is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if product_price is None or product_price == "":
        return Response({
            "status": False,
            "message": "Product price is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if stock_number is None or stock_number == "":
        return Response({
            "status": False,
            "message": "Stock number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not category:
        return Response({
            "status": False,
            "message": "Category is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not brand_name:
        return Response({
            "status": False,
            "message": "Brand name is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_name:
        return Response({
            "status": False,
            "message": "Vehicle name is required"
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        product_price = float(product_price)
        if product_price < 0:
            return Response({
                "status": False,
                "message": "Product price cannot be negative"
            }, status=status.HTTP_400_BAD_REQUEST)

    except (ValueError, TypeError):

        return Response({
            "status": False,
            "message": "Invalid product price"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:

        stock_number = int(stock_number)
        if stock_number < 0:
            return Response({
                "status": False,
                "message": "Stock number cannot be negative"
            }, status=status.HTTP_400_BAD_REQUEST)

    except (ValueError, TypeError):

        return Response({
            "status": False,
            "message": "Invalid stock number"
        }, status=status.HTTP_400_BAD_REQUEST)

    if product_image:
        # Maximum 5 MB

        if product_image.size > 5 * 1024 * 1024:

            return Response({
                "status": False,
                "message": "Product image should not exceed 5 MB"
            }, status=status.HTTP_400_BAD_REQUEST)

    try:

        product_image_url = None
        file_name = None

        # Upload image if provided
        if product_image:

            product_image_url, file_name = upload_image(
                product_image,
                "product",
                user.u_id
            )

            print("IMAGE URL:", product_image_url)
            print("FILE NAME:", file_name)

        product = Products.objects.create(
            user=user,
            product_name=product_name,
            product_price=product_price,
            stock_number=stock_number,
            category=category,
            brand_name=brand_name,
            vehicle_name=vehicle_name,
            description=description,
            product_image_url=product_image_url,
            is_available = True
        )

        print("PRODUCT ID:", product.product_id)
        print("USER ID:", user.u_id)
        print("SAVED DB URL:", product.product_image_url)
        save_notification(user.u_id, "Product Added Successfully", "Product Notification")

        return Response({
            "status": True,
            "message": "Product added successfully",
            "data": {
                "product_id": product.product_id,
                "u_id": user.u_id,
                "product_name": product.product_name,
                "product_price": str(product.product_price),
                "stock_number": product.stock_number,
                "category": product.category,
                "brand_name": product.brand_name,
                "vehicle_name": product.vehicle_name,
                "description": product.description,
                "product_image_url": product.product_image_url,
                "created_at": product.created_at,
                "updated_at": product.updated_at
            }

        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print("ADD PRODUCT ERROR:", repr(e))
        return Response({
            "status": False,
            "message": "Failed to add product",
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_products(request):

    # Logged-in user from Bearer token
    user = request.user

    # Get only products belonging to logged-in user
    products = Products.objects.filter(
        user=user
    ).order_by('-created_at')

    product_list = []

    for product in products:

        product_list.append({
            "product_id": product.product_id,
            "u_id": product.user.u_id,
            "product_name": product.product_name,
            "product_price": str(product.product_price),
            "stock_number": product.stock_number,
            "category": product.category,
            "brand_name": product.brand_name,
            "vehicle_name": product.vehicle_name,
            "description": product.description,
            "product_image_url": product.product_image_url,
            "created_at": product.created_at,
            "updated_at": product.updated_at
        })

    return Response({
        "status": True,
        "message": "Products fetched successfully",
        "data": product_list
    }, status=status.HTTP_200_OK)


@api_view(['PUT'])
@authentication_classes([BearerAuthentication])
def update_product_stock(request, product_id):

    user = request.user

    stock_number = request.data.get('stock_number')

    if stock_number is None or stock_number == "":
        return Response({
            "status": False,
            "message": "Stock number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate stock
    try:
        stock_number = int(stock_number)

        if stock_number < 0:
            return Response({
                "status": False,
                "message": "Stock number cannot be negative"
            }, status=status.HTTP_400_BAD_REQUEST)

    except (ValueError, TypeError):
        return Response({
            "status": False,
            "message": "Invalid stock number"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:

        # Only allow logged-in user to update his own product
        product = Products.objects.get(
            product_id=product_id,
            user=user
        )

    except Products.DoesNotExist:

        return Response({
            "status": False,
            "message": "Product not found"
        }, status=status.HTTP_404_NOT_FOUND)

    # Update stock
    product.stock_number = stock_number
    product.save(update_fields=[
        'stock_number',
        'updated_at'
    ])
    save_notification(user.u_id, "Inventory Updated with new stock", "Product Notification")

    return Response({
        "status": True,
        "message": "Stock updated successfully",
        "data": {
            "product_id": product.product_id,
            "u_id": user.u_id,
            "product_name": product.product_name,
            "stock_number": product.stock_number,
            "is_available": product.is_available,
            "updated_at": product.updated_at
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT'])
@authentication_classes([BearerAuthentication])
def update_product_availability(request, product_id):

    user = request.user

    is_available = request.data.get('is_available')

    if is_available is None:
        return Response({
            "status": False,
            "message": "is_available is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Convert string values from Postman
    if isinstance(is_available, str):

        if is_available.lower() == "true":
            is_available = True

        elif is_available.lower() == "false":
            is_available = False

        else:
            return Response({
                "status": False,
                "message": "is_available must be true or false"
            }, status=status.HTTP_400_BAD_REQUEST)

    elif not isinstance(is_available, bool):

        return Response({
            "status": False,
            "message": "is_available must be true or false"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:

        # Only logged-in user's product
        product = Products.objects.get(
            product_id=product_id,
            user=user
        )

    except Products.DoesNotExist:

        return Response({
            "status": False,
            "message": "Product not found"
        }, status=status.HTTP_404_NOT_FOUND)

    # Update availability
    product.is_available = is_available

    product.save(update_fields=[
        'is_available',
        'updated_at'
    ])
    save_notification(user.u_id, "You have emarked one of your product is currently Unavailable", "Product Notification")

    return Response({
        "status": True,
        "message": (
            "Product activated successfully"
            if is_available
            else "Product paused successfully"
        ),
        "data": {
            "product_id": product.product_id,
            "u_id": user.u_id,
            "product_name": product.product_name,
            "stock_number": product.stock_number,
            "is_available": product.is_available,
            "updated_at": product.updated_at
        }
    }, status=status.HTTP_200_OK)

@api_view(['DELETE'])
@authentication_classes([BearerAuthentication])
def delete_product(request, product_id):

    # Logged-in user from Bearer token
    user = request.user

    try:
        # Find only the product belonging to logged-in user
        product = Products.objects.get(
            product_id=product_id,
            user=user
        )

    except Products.DoesNotExist:
        return Response({
            "status": False,
            "message": "Product not found"
        }, status=status.HTTP_404_NOT_FOUND)

    # Store details before deleting
    deleted_product_id = product.product_id
    deleted_product_name = product.product_name

    # Delete product
    product.delete()
    save_notification(user.u_id, "Your product is deleted successfully", "Product Notification")

    return Response({
        "status": True,
        "message": "Product deleted successfully",
        "data": {
            "product_id": deleted_product_id,
            "product_name": deleted_product_name,
            "u_id": user.u_id
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_all_products(request):

    products = Products.objects.all().order_by('-created_at')

    product_list = []

    for product in products:

        if product.stock_number <= 0:
            stock_status = "out_of_stock"
        elif product.is_available:
            stock_status = "available"
        else:
            stock_status = "unavailable"

        product_list.append({
            "product_id": product.product_id,
            "u_id": product.user.u_id,
            "product_name": product.product_name,
            "product_price": str(product.product_price),
            "stock_number": product.stock_number,
            "category": product.category,
            "brand_name": product.brand_name,
            "vehicle_name": product.vehicle_name,
            "description": product.description,
            "product_image_url": product.product_image_url,
            "is_available": product.is_available,
            "stock_status": stock_status,
            "created_at": product.created_at,
            "updated_at": product.updated_at
        })

    return Response({
        "status": True,
        "message": "All products fetched successfully",
        "count": len(product_list),
        "data": product_list
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_owners(request):
    owners = User.objects.filter(
        role__role_code='OWN',
        is_active=True
    ).select_related('role').order_by('-created_at')

    owner_list = []

    for owner in owners:

        owner_list.append({
            "u_id": owner.u_id,
            "name": owner.name,
            "number": owner.number,
            "subscribed": owner.subscribed,
            "profile_image_url": owner.profile_image_url,

            # 👇 NEW fields
            "shop_open": owner.shop_open,
            "emergency_service": owner.emergency_service,

            "role": {
                "role_id": owner.role.role_id,
                "role_name": owner.role.role_name,
                "role_code": owner.role.role_code
            },

            "created_at": owner.created_at,
            "updated_at": owner.updated_at
        })

    return Response({
        "status": True,
        "message": "Owners fetched successfully",
        "count": len(owner_list),
        "data": owner_list
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def create_appointment(request):

    customer = request.user
    service_center_u_id = request.data.get('service_center_u_id')
    vehicle_model = request.data.get('vehicle_model')
    vehicle_number = request.data.get('vehicle_number')
    service_type = request.data.get('service_type')
    description = request.data.get('description')
    estimated_cost = request.data.get('estimated_cost')
    appointment_date = request.data.get('appointment_date')
    appointment_time = request.data.get('appointment_time')

    if not service_center_u_id:
        return Response({
            "status": False,
            "message": "Service center is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_model:
        return Response({
            "status": False,
            "message": "Vehicle model is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_number:
        return Response({
            "status": False,
            "message": "Vehicle number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not service_type:
        return Response({
            "status": False,
            "message": "Service type is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not appointment_date:
        return Response({
            "status": False,
            "message": "Appointment date is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not appointment_time:
        return Response({
            "status": False,
            "message": "Appointment time is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:

        service_center = User.objects.select_related('role').get(u_id=service_center_u_id,is_active=True)
    except User.DoesNotExist:
        return Response({
            "status": False,
            "message": "Service center not found"
        }, status=status.HTTP_404_NOT_FOUND)

    role_code = (
        service_center.role.role_code or ""
    ).strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Selected user is not a service center",
            "data": {
                "u_id": service_center.u_id,
                "role_name": service_center.role.role_name,
                "role_code": service_center.role.role_code
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    if estimated_cost not in [None, ""]:
        try:
            estimated_cost = float(estimated_cost)
            if estimated_cost < 0:
                return Response({
                    "status": False,
                    "message": "Estimated cost cannot be negative"
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                "status": False,
                "message": "Invalid estimated cost"
            }, status=status.HTTP_400_BAD_REQUEST)
    else:
        estimated_cost = None

    try:
        appointment_date = datetime.strptime(
            str(appointment_date),
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return Response({
            "status": False,
            "message": "Invalid appointment date. Use YYYY-MM-DD"
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        appointment_time = datetime.strptime(
            str(appointment_time),
            "%H:%M"
        ).time()
    except (ValueError, TypeError):
        return Response({
            "status": False,
            "message": "Invalid appointment time. Use HH:MM"
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        appointment = Appointments.objects.create(
            service_center=service_center,
            customer=customer,
            vehicle_model=vehicle_model,
            vehicle_number=vehicle_number,
            service_type=service_type,
            description=description,
            estimated_cost=estimated_cost,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            status='pending'
        )
        try:
            channel_layer = get_channel_layer()
            async_to_sync(
                channel_layer.group_send
            )(
                f"notifications_{service_center.u_id}",
                {
                    "type": "send_notification",
                    "data": {
                        "type": "new_appointment",
                        "message": "New appointment booked",
                        "appointment_id": appointment.appointment_id,
                        "customer": {
                            "u_id": customer.u_id,
                            "name": customer.name,
                            "number": customer.number
                        },
                        "service_center": {
                            "u_id": service_center.u_id,
                            "name": service_center.name,
                            "number": service_center.number
                        },
                        "vehicle": {
                            "model": appointment.vehicle_model,
                            "number": appointment.vehicle_number
                        },
                        "service_type": appointment.service_type,
                        "description": appointment.description,
                        "estimated_cost": (
                            str(appointment.estimated_cost)
                            if appointment.estimated_cost is not None
                            else None
                        ),
                        "appointment_date": str(appointment.appointment_date),
                        "appointment_time": str(appointment.appointment_time),
                        "status": appointment.status,

                        "created_at": 
                        (
                            appointment.created_at.isoformat()
                            if appointment.created_at
                            else None
                        )
                    }
                }
            )
            print("WEBSOCKET NOTIFICATION SENT TO:",service_center.u_id)
        except Exception as websocket_error:
            print("WEBSOCKET ERROR:", repr(websocket_error))
        
        try:
            save_notification(
                customer.u_id,
                f"Appointment created successfully with reference: {appointment.vehicle_number}",
                "Appointment Notification"
            )
        except Exception as notif_err:
            print("CUSTOMER NOTIFICATION ERROR:", repr(notif_err))

        try:
            save_notification(
                service_center.u_id,
                f"New appointment from {customer.name} — {appointment.vehicle_number}",
                "New Appointment"
            )
        except Exception as notif_err:
            print("OWNER NOTIFICATION ERROR:", repr(notif_err))
        return Response({

            "status": True,
            "message": "Appointment created successfully",
            "data": {
                "appointment_id":
                    appointment.appointment_id,
                "service_center": {
                    "u_id":service_center.u_id,
                    "name":service_center.name,
                    "number":service_center.number,
                    "profile_image_url":service_center.profile_image_url
                },
                "customer": {
                    "u_id":customer.u_id,
                    "name":customer.name,
                    "number":customer.number
                },
                "vehicle_model":appointment.vehicle_model,
                "vehicle_number":appointment.vehicle_number,
                "service_type":appointment.service_type,
                "description":appointment.description,

                "estimated_cost": (str(appointment.estimated_cost)
                    if appointment.estimated_cost is not None
                    else None
                ),
                "appointment_date":appointment.appointment_date,
                "appointment_time":appointment.appointment_time,
                "status":appointment.status,
                "created_at":appointment.created_at,
                "updated_at":appointment.updated_at
            }

        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(
            "CREATE APPOINTMENT ERROR:",
            repr(e)
        )
        return Response({
            "status": False,
            "message":"Failed to create appointment",
            "error":str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_my_appointments(request):

    user = request.user
    appointments = Appointments.objects.filter(
        customer=user
    ).select_related(
        'service_center',
        'service_center__role'
    ).order_by('-created_at')
    appointment_list = []
    for appointment in appointments:

        appointment_list.append({
            "appointment_id": appointment.appointment_id,

            # Service Center / Owner
            "service_center": {
                "u_id": appointment.service_center.u_id,
                "name": appointment.service_center.name,
                "number": appointment.service_center.number,
                "profile_image_url": appointment.service_center.profile_image_url
            },

            # Customer / Logged-in User
            "customer": {
                "u_id": user.u_id,
                "name": user.name,
                "number": user.number,
            },

            # Vehicle
            "vehicle_model": appointment.vehicle_model,
            "vehicle_number": appointment.vehicle_number,

            # Service
            "service_type": appointment.service_type,
            "description": appointment.description,
            "estimated_cost": (
                str(appointment.estimated_cost)
                if appointment.estimated_cost is not None
                else None
            ),

            # Schedule
            "appointment_date": appointment.appointment_date,
            "appointment_time": appointment.appointment_time,

            # Status
            "status": appointment.status,

            "created_at": appointment.created_at,
            "updated_at": appointment.updated_at
        })

    return Response({
        "status": True,
        "message": "Appointments fetched successfully",
        "count": len(appointment_list),
        "data": appointment_list
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_received_appointments(request):
    owner = request.user
    role_code = (
        owner.role.role_code or ""
    ).strip().upper()
    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can access received appointments"
        }, status=status.HTTP_403_FORBIDDEN)

    appointments = Appointments.objects.filter(service_center=owner).select_related('service_center','customer',
        'customer__role').order_by('-created_at')

    appointment_list = []

    for appointment in appointments:
        appointment_list.append({
            "appointment_id":appointment.appointment_id,
            "service_center": {
                "u_id": owner.u_id,
                "name":owner.name,
                "number":owner.number,
                "profile_image_url":owner.profile_image_url
            },

            "customer": {
                "u_id": appointment.customer.u_id,
                "name": appointment.customer.name,
                "number": appointment.customer.number,
                "profile_image_url":appointment.customer.profile_image_url
            },

            "vehicle_model":appointment.vehicle_model,
            "vehicle_number":appointment.vehicle_number,
            "service_type":appointment.service_type,
            "description": appointment.description,

            "estimated_cost": (
                str(appointment.estimated_cost)
                if appointment.estimated_cost is not None
                else None
            ),
            "appointment_date": appointment.appointment_date,
            "appointment_time":appointment.appointment_time,
            "status":appointment.status,
            "created_at":appointment.created_at,
            "updated_at":appointment.updated_at
        })

    return Response({
        "status": True,
        "message":"Received appointments fetched successfully",
        "count":len(appointment_list),
        "data":appointment_list
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'POST'])
@authentication_classes([BearerAuthentication])
def update_appointment_status(request, appointment_id):
    # Logged-in user must be an OWNER
    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can update appointments"
        }, status=status.HTTP_403_FORBIDDEN)

    # Validate status
    new_status = (request.data.get('status') or '').strip().lower()

    ALLOWED = ['accepted', 'rejected', 'in_progress', 'completed']

    if new_status not in ALLOWED:
        return Response({
            "status": False,
            "message": f"Invalid status. Allowed: {', '.join(ALLOWED)}"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Fetch appointment belonging to this owner
    try:
        appointment = Appointments.objects.select_related(
            'service_center', 'customer'
        ).get(
            appointment_id=appointment_id,
            service_center=owner
        )
    except Appointments.DoesNotExist:
        return Response({
            "status": False,
            "message": "Appointment not found"
        }, status=status.HTTP_404_NOT_FOUND)

    # Update status
    appointment.status = new_status
    appointment.save(update_fields=['status', 'updated_at'])

    broadcast_payload = {
        "type": "appointment_status_changed",
        "data": {
            "type": "appointment_status_changed",
            "appointment_id": appointment.appointment_id,
            "status": appointment.status,
            "customer": {
                "u_id": appointment.customer.u_id,
                "name": appointment.customer.name,
                "number": appointment.customer.number,
            },
            "service_center": {
                "u_id": owner.u_id,
                "name": owner.name,
                "number": owner.number,
            },
            "vehicle_model": appointment.vehicle_model,
            "vehicle_number": appointment.vehicle_number,
            "service_type": appointment.service_type,
            "description": appointment.description,
            "estimated_cost": (
                str(appointment.estimated_cost)
                if appointment.estimated_cost is not None else None
            ),
            "appointment_date": str(appointment.appointment_date),
            "appointment_time": str(appointment.appointment_time),
            "created_at": (
                appointment.created_at.isoformat()
                if appointment.created_at else None
            ),
            "updated_at": (
                appointment.updated_at.isoformat()
                if appointment.updated_at else None
            ),
        }
    }
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notifications_{owner.u_id}",
            broadcast_payload
        )
        async_to_sync(channel_layer.group_send)(
            f"notifications_{appointment.customer.u_id}",
            broadcast_payload
        )
        print(
            f"WEBSOCKET STATUS BROADCAST: "
            f"appt={appointment.appointment_id} "
            f"status={new_status} "
            f"owner={owner.u_id} customer={appointment.customer.u_id}"
        )

    except Exception as ws_err:
        print("WEBSOCKET STATUS ERROR:", repr(ws_err))

    save_notification(owner.u_id, "Appointment status has been changed", "Appointment Notification")

    return Response({
        "status": True,
        "message": f"Appointment {new_status} successfully",
        "data": {
            "appointment_id": appointment.appointment_id,
            "status": appointment.status,
            "updated_at": appointment.updated_at,
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def create_emergency_appointment(request):

    customer = request.user
    service_center_u_id = request.data.get('service_center_u_id')
    vehicle_model       = request.data.get('vehicle_model')
    vehicle_number      = request.data.get('vehicle_number')
    description         = request.data.get('description')
    location            = request.data.get('location')
    issue_photo_urls    = request.data.get('issue_photo_urls')  # optional: list[str]


    if not service_center_u_id:
        return Response({
            "status": False,
            "message": "Service center is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_model:
        return Response({
            "status": False,
            "message": "Vehicle model is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_number:
        return Response({
            "status": False,
            "message": "Vehicle number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        service_center = User.objects.select_related('role').get(
            u_id=service_center_u_id,
            is_active=True
        )
    except User.DoesNotExist:
        return Response({
            "status": False,
            "message": "Service center not found"
        }, status=status.HTTP_404_NOT_FOUND)

    role_code = (service_center.role.role_code or "").strip().upper()
    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Selected user is not a service center",
            "data": {
                "u_id": service_center.u_id,
                "role_name": service_center.role.role_name,
                "role_code": service_center.role.role_code
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    if issue_photo_urls is not None and not isinstance(issue_photo_urls, list):
        return Response({
            "status": False,
            "message": "issue_photo_urls must be a list of URLs"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        emergency = EmergencyAppointments.objects.create(
            service_center=service_center,
            customer=customer,
            vehicle_model=vehicle_model,
            vehicle_number=vehicle_number,
            description=description,
            location=location,
            issue_photo_urls=issue_photo_urls or [],
            status='pending'
        )
        try:
            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                f"notifications_{service_center.u_id}",
                {
                    "type": "send_notification",
                    "data": {
                        "type": "new_emergency",
                        "message": "New emergency request received",
                        "emergency_id": emergency.emergency_id,
                        "customer": {
                            "u_id":   customer.u_id,
                            "name":   customer.name,
                            "number": customer.number,
                        },
                        "service_center": {
                            "u_id":   service_center.u_id,
                            "name":   service_center.name,
                            "number": service_center.number,
                        },
                        "vehicle_model":  emergency.vehicle_model,
                        "vehicle_number": emergency.vehicle_number,
                        "description": emergency.description,
                        "location":    emergency.location,
                        "issue_photo_urls": emergency.issue_photo_urls or [],
                        "status": emergency.status,

                        "created_at": (
                            emergency.created_at.isoformat()
                            if emergency.created_at else None
                        ),
                    }
                }
            )

            print("EMERGENCY WS SENT TO:", service_center.u_id)

        except Exception as ws_err:
            print("EMERGENCY WS ERROR:", repr(ws_err))

        # SUCCESS RESPONSE
        return Response({
            "status": True,
            "message": "Emergency appointment created successfully",
            "data": {
                "emergency_id": emergency.emergency_id,

                "service_center": {
                    "u_id":   service_center.u_id,
                    "name":   service_center.name,
                    "number": service_center.number,
                    "profile_image_url": service_center.profile_image_url,
                },

                "customer": {
                    "u_id":   customer.u_id,
                    "name":   customer.name,
                    "number": customer.number,
                },
                "vehicle_model":  emergency.vehicle_model,
                "vehicle_number": emergency.vehicle_number,
                "description": emergency.description,
                "location":    emergency.location,
                "issue_photo_urls": emergency.issue_photo_urls or [],
                "status": emergency.status,
                "created_at": emergency.created_at,
                "updated_at": emergency.updated_at,
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print("CREATE EMERGENCY ERROR:", repr(e))
        return Response({
            "status": False,
            "message": "Failed to create emergency appointment",
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_received_emergencies(request):

    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can access emergency requests"
        }, status=status.HTTP_403_FORBIDDEN)

    emergencies = EmergencyAppointments.objects.filter(
        service_center=owner
    ).select_related(
        'service_center', 'customer'
    ).order_by('-created_at')

    data = []
    for e in emergencies:
        data.append({
            "emergency_id": e.emergency_id,

            "service_center": {
                "u_id": e.service_center.u_id,
                "name": e.service_center.name,
                "number": e.service_center.number,
                "profile_image_url": e.service_center.profile_image_url,
            },

            "customer": {
                "u_id": e.customer.u_id,
                "name": e.customer.name,
                "number": e.customer.number,
            },

            "vehicle_model":  e.vehicle_model,
            "vehicle_number": e.vehicle_number,
            "description":    e.description,
            "location":       e.location,
            "issue_photo_urls": e.issue_photo_urls or [],
            "status":         e.status,

            "created_at": e.created_at,
            "updated_at": e.updated_at,
        })

    return Response({
        "status": True,
        "message": "Emergencies fetched successfully",
        "count": len(data),
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_my_emergencies(request):
 
    user = request.user
    emergencies = EmergencyAppointments.objects.filter(
        customer=user
    ).select_related(
        'service_center',
        'service_center__role'
    ).order_by('-created_at')
    data = []
    for e in emergencies:
        data.append({
            "emergency_id": e.emergency_id,
            "service_center": {
                "u_id": e.service_center.u_id,
                "name": e.service_center.name,
                "number": e.service_center.number,
                "profile_image_url": e.service_center.profile_image_url,
            },
            "customer": {
                "u_id": user.u_id,
                "name": user.name,
                "number": user.number,
            },
            "vehicle_model":  e.vehicle_model,
            "vehicle_number": e.vehicle_number,
            "description":      e.description,
            "location":         e.location,
            "issue_photo_urls": e.issue_photo_urls or [],
            "status": e.status,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        })

    return Response({
        "status": True,
        "message": "Your emergency appointments fetched successfully",
        "count": len(data),
        "data": data
    }, status=status.HTTP_200_OK)

@api_view(['PUT', 'POST'])
@authentication_classes([BearerAuthentication])
def update_emergency_status(request, emergency_id):

    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can update emergencies"
        }, status=status.HTTP_403_FORBIDDEN)

    new_status = (request.data.get('status') or '').strip().lower()

    ALLOWED = ['accepted', 'rejected', 'en_route', 'in_progress', 'completed']

    if new_status not in ALLOWED:
        return Response({
            "status": False,
            "message": f"Invalid status. Allowed: {', '.join(ALLOWED)}"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        emergency = EmergencyAppointments.objects.select_related(
            'service_center', 'customer'
        ).get(
            emergency_id=emergency_id,
            service_center=owner
        )
    except EmergencyAppointments.DoesNotExist:
        return Response({
            "status": False,
            "message": "Emergency not found"
        }, status=status.HTTP_404_NOT_FOUND)

    emergency.status = new_status
    emergency.save(update_fields=['status', 'updated_at'])

    return Response({
        "status": True,
        "message": f"Emergency {new_status} successfully",
        "data": {
            "emergency_id": emergency.emergency_id,
            "status": emergency.status,
            "updated_at": emergency.updated_at,
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def create_bill(request):
  
    owner = request.user

    customer_name = (request.data.get('customer_name') or '').strip()
    phone_number = (request.data.get('phone_number') or '').strip()
    vehicle_number = (request.data.get('vehicle_number') or '').strip()
    tax_percentage = request.data.get('tax_percentage', 10)
    items = request.data.get('items') or []


    if not phone_number:
        return Response({
            "status": False,
            "message": "Phone number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not vehicle_number:
        return Response({
            "status": False,
            "message": "Vehicle number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not items or not isinstance(items, list):
        return Response({
            "status": False,
            "message": "At least one service item is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    customer = User.objects.filter(
        number=phone_number,
        is_active=True
    ).select_related('role').first()

    if customer is None:
        return Response({
            "status": False,
            "message": f"No customer found with phone {phone_number}. Please register the customer first."
        }, status=status.HTTP_404_NOT_FOUND)


    try:
        tax_pct = Decimal(str(tax_percentage))
        if tax_pct < 0 or tax_pct > 100:
            raise ValueError('tax_percentage out of range')

        subtotal = Decimal('0')
        validated_items = []

        for it in items:
            name = (it.get('service_name') or '').strip()
            qty = int(it.get('quantity') or 0)
            price = Decimal(str(it.get('service_price') or 0))

            if not name:
                return Response({
                    "status": False,
                    "message": "Each item needs a service_name"
                }, status=status.HTTP_400_BAD_REQUEST)

            if qty <= 0:
                return Response({
                    "status": False,
                    "message": f"Invalid quantity for {name}"
                }, status=status.HTTP_400_BAD_REQUEST)

            if price < 0:
                return Response({
                    "status": False,
                    "message": f"Invalid price for {name}"
                }, status=status.HTTP_400_BAD_REQUEST)

            line_total = Decimal(qty) * price
            subtotal += line_total

            validated_items.append({
                'service_name': name,
                'quantity': qty,
                'service_price': price,
                'total_price': line_total,
            })

        tax_amount = (subtotal * tax_pct / Decimal('100')).quantize(Decimal('0.01'))
        total_amount = (subtotal + tax_amount).quantize(Decimal('0.01'))

    except (InvalidOperation, ValueError, TypeError) as e:
        return Response({
            "status": False,
            "message": f"Invalid bill data: {e}"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        bill = GeneratedBills.objects.create(
            owner=owner,
            customer=customer,
            customer_name=customer_name or customer.name,
            phone_number=phone_number,
            vehicle_number=vehicle_number,
            subtotal=subtotal,
            tax_percentage=tax_pct,
            tax_amount=tax_amount,
            total_amount=total_amount,
        )

        for it in validated_items:
            GeneratedBillServices.objects.create(
                bill=bill,
                service_name=it['service_name'],
                quantity=it['quantity'],
                service_price=it['service_price'],
                total_price=it['total_price'],
            )
        try:
            save_notification(
                customer.u_id,
                f"Bill #{bill.bill_id} generated — ₹{total_amount}",
                "Bill Notification"
            )
        except Exception as e:
            print("CUSTOMER BILL NOTIF ERROR:", repr(e))

        try:
            save_notification(
                owner.u_id,
                f"Bill #{bill.bill_id} issued to {customer.name} — ₹{total_amount}",
                "Bill Notification"
            )
        except Exception as e:
            print("OWNER BILL NOTIF ERROR:", repr(e))

        return Response({
            "status": True,
            "message": "Bill created successfully",
            "data": {
                "bill_id": bill.bill_id,
                "owner": {
                    "u_id": owner.u_id,
                    "name": owner.name,
                    "number": owner.number,
                },
                "customer": {
                    "u_id": customer.u_id,
                    "name": customer.name,
                    "number": customer.number,
                },
                "customer_name": bill.customer_name,
                "phone_number": bill.phone_number,
                "vehicle_number": bill.vehicle_number,
                "services": [
                    {
                        "bill_service_id": s.bill_service_id,
                        "service_name": s.service_name,
                        "quantity": s.quantity,
                        "service_price": str(s.service_price),
                        "total_price": str(s.total_price),
                    }
                    for s in bill.services.all()
                ],
                "subtotal": str(bill.subtotal),
                "tax_percentage": str(bill.tax_percentage),
                "tax_amount": str(bill.tax_amount),
                "total_amount": str(bill.total_amount),
                "generated_at": bill.generated_at,
                "updated_at": bill.updated_at,
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print("CREATE BILL ERROR:", repr(e))
        return Response({
            "status": False,
            "message": "Failed to create bill",
            "error": str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_bills(request):
    
    user = request.user
    role_code = (user.role.role_code or "").strip().upper()
    if role_code == "OWN":
        qs = GeneratedBills.objects.filter(owner=user)
    else:
        qs = GeneratedBills.objects.filter(customer=user)
    qs = qs.select_related('owner','customer',).prefetch_related('services').order_by('-generated_at')
    data = []
    for bill in qs:
        data.append({
            "bill_id": bill.bill_id,

            "owner": {
                "u_id": bill.owner.u_id,
                "name": bill.owner.name,
                "number": bill.owner.number,
            },

            "customer": {
                "u_id": bill.customer.u_id,
                "name": bill.customer.name,
                "number": bill.customer.number,
            },

            "customer_name": bill.customer_name,
            "phone_number": bill.phone_number,
            "vehicle_number": bill.vehicle_number,

            "services": [
                {
                    "bill_service_id": s.bill_service_id,
                    "service_name": s.service_name,
                    "quantity": s.quantity,
                    "service_price": str(s.service_price),
                    "total_price": str(s.total_price),
                }
                for s in bill.services.all()
            ],

            "subtotal": str(bill.subtotal),
            "tax_percentage": str(bill.tax_percentage),
            "tax_amount": str(bill.tax_amount),
            "total_amount": str(bill.total_amount),

            "generated_at": bill.generated_at,
            "updated_at": bill.updated_at,
        })

    return Response({
        "status": True,
        "message": "Bills fetched successfully",
        "count": len(data),
        "data": data,
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'POST'])
@authentication_classes([BearerAuthentication])
def update_shop_status(request):

    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can update shop status"
        }, status=status.HTTP_403_FORBIDDEN)

    if 'shop_open' not in request.data:
        return Response({
            "status": False,
            "message": "shop_open field is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    shop_open = bool(request.data.get('shop_open'))

    owner.shop_open = shop_open
    owner.save(update_fields=['shop_open', 'updated_at'])

    return Response({
        "status": True,
        "message": "Shop is now OPEN" if shop_open else "Shop is now CLOSED",
        "data": {
            "u_id": owner.u_id,
            "shop_open": owner.shop_open,
            "updated_at": owner.updated_at,
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'POST'])
@authentication_classes([BearerAuthentication])
def update_emergency_service(request):

    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()

    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can update emergency service"
        }, status=status.HTTP_403_FORBIDDEN)

    if 'emergency_service' not in request.data:
        return Response({
            "status": False,
            "message": "emergency_service field is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    emergency_service = bool(request.data.get('emergency_service'))

    owner.emergency_service = emergency_service
    owner.save(update_fields=['emergency_service', 'updated_at'])

    return Response({
        "status": True,
        "message": (
            "Emergency service is now ON"
            if emergency_service
            else "Emergency service is now OFF"
        ),
        "data": {
            "u_id": owner.u_id,
            "emergency_service": owner.emergency_service,
            "updated_at": owner.updated_at,
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([BearerAuthentication])
def place_order(request):
    
    customer = request.user
    customer_name = (request.data.get('customer_name') or '').strip()
    phone_number = (request.data.get('phone_number') or '').strip()
    address_line = (request.data.get('address_line') or '').strip()
    city = (request.data.get('city') or '').strip()
    state_name = (request.data.get('state') or '').strip()
    pincode = (request.data.get('pincode') or '').strip()
    landmark = (request.data.get('landmark') or '').strip()
    payment_method = (request.data.get('payment_method') or 'cod').strip()
    items = request.data.get('items') or []

    if not customer_name:
        return Response({
            "status": False,
            "message": "Customer name is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not phone_number:
        return Response({
            "status": False,
            "message": "Phone number is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not address_line:
        return Response({
            "status": False,
            "message": "Address is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not city:
        return Response({
            "status": False,
            "message": "City is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not state_name:
        return Response({
            "status": False,
            "message": "State is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not pincode:
        return Response({
            "status": False,
            "message": "Pincode is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not items or not isinstance(items, list):
        return Response({
            "status": False,
            "message": "At least one item is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        subtotal = Decimal('0')
        validated_items = []
        owner_ids = set()

        for it in items:
            product_id = it.get('product_id')
            qty = int(it.get('quantity') or 0)

            if not product_id:
                return Response({
                    "status": False,
                    "message": "product_id missing in one item"
                }, status=status.HTTP_400_BAD_REQUEST)

            if qty <= 0:
                return Response({
                    "status": False,
                    "message": "Invalid quantity"
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                product = Products.objects.select_related('user').get(
                    product_id=product_id
                )
            except Products.DoesNotExist:
                return Response({
                    "status": False,
                    "message": f"Product {product_id} not found"
                }, status=status.HTTP_404_NOT_FOUND)

            if hasattr(product, 'is_available') and not product.is_available:
                return Response({
                    "status": False,
                    "message": f"{product.product_name} is currently unavailable"
                }, status=status.HTTP_400_BAD_REQUEST)

            if product.stock_number < qty:
                return Response({
                    "status": False,
                    "message": f"Only {product.stock_number} left for {product.product_name}"
                }, status=status.HTTP_400_BAD_REQUEST)

            if not product.user:
                return Response({
                    "status": False,
                    "message": f"{product.product_name} has no seller attached"
                }, status=status.HTTP_400_BAD_REQUEST)

            owner_ids.add(product.user.u_id)

            price = Decimal(str(product.product_price))
            line_total = price * qty
            subtotal += line_total

            validated_items.append({
                'product': product,
                'product_name': product.product_name,
                'product_price': price,
                'quantity': qty,
                'total_price': line_total,
            })

        if len(owner_ids) == 0:
            return Response({
                "status": False,
                "message": "No valid products in the order"
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(owner_ids) > 1:
            return Response({
                "status": False,
                "message": "All products in one order must belong to the same seller. Please split the cart."
            }, status=status.HTTP_400_BAD_REQUEST)

        owner_id = next(iter(owner_ids))
        owner = User.objects.filter(u_id=owner_id, is_active=True).first()
        if owner is None:
            return Response({
                "status": False,
                "message": "Seller not found"
            }, status=status.HTTP_404_NOT_FOUND)

        tax_amount = (subtotal * Decimal('0.0')).quantize(Decimal('0.01'))
        delivery_charge = Decimal('0.00')
        total_amount = (subtotal + tax_amount + delivery_charge).quantize(Decimal('0.01'))

    except (InvalidOperation, ValueError, TypeError) as e:
        return Response({
            "status": False,
            "message": f"Invalid order data: {e}"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():

            order = Order.objects.create(
                customer=customer,
                owner=owner,
                customer_name=customer_name,
                phone_number=phone_number,
                address_line=address_line,
                city=city,
                state=state_name,
                pincode=pincode,
                landmark=landmark or None,
                subtotal=subtotal,
                tax_amount=tax_amount,
                delivery_charge=delivery_charge,
                total_amount=total_amount,
                payment_method=payment_method,
                status='pending',
                payment_status='unpaid',
            )

            for it in validated_items:
                OrderItem.objects.create(
                    order=order,
                    product=it['product'],
                    product_name=it['product_name'],
                    product_price=it['product_price'],
                    quantity=it['quantity'],
                    total_price=it['total_price'],
                )

                product = it['product']
                product.stock_number -= it['quantity']

                if product.stock_number <= 0:
                    product.stock_number = 0
                    product.is_available = False
                    product.save(update_fields=[
                        'stock_number', 'is_available', 'updated_at'
                    ])
                else:
                    product.save(update_fields=[
                        'stock_number', 'updated_at'
                    ])

        try:
            save_notification(
                customer.u_id,
                f"Order #{order.order_id} placed — ₹{total_amount}",
                "Order Notification",
            )
        except Exception as e:
            print("CUSTOMER ORDER NOTIF ERROR:", repr(e))

        try:
            save_notification(
                owner.u_id,
                f"New order #{order.order_id} from {customer_name} — ₹{total_amount}",
                "New Order",
            )
        except Exception as e:
            print("OWNER ORDER NOTIF ERROR:", repr(e))

        return Response({
            "status": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": order.order_id,

                "customer": {
                    "u_id": customer.u_id,
                    "name": customer.name,
                    "number": customer.number,
                },
                "owner": {
                    "u_id": owner.u_id,
                    "name": owner.name,
                    "number": owner.number,
                },

                "customer_name": order.customer_name,
                "phone_number": order.phone_number,
                "address_line": order.address_line,
                "city": order.city,
                "state": order.state,
                "pincode": order.pincode,
                "landmark": order.landmark,

                "items": [
                    {
                        "product_id": it.product.product_id if it.product else None,
                        "product_name": it.product_name,
                        "product_price": str(it.product_price),
                        "quantity": it.quantity,
                        "total_price": str(it.total_price),
                    }
                    for it in order.items.select_related('product').all()
                ],

                "subtotal": str(order.subtotal),
                "tax_amount": str(order.tax_amount),
                "delivery_charge": str(order.delivery_charge),
                "total_amount": str(order.total_amount),

                "payment_method": order.payment_method,
                "payment_status": order.payment_status,
                "status": order.status,
                "placed_at": order.placed_at,
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print("PLACE ORDER ERROR:", repr(e))
        return Response({
            "status": False,
            "message": "Failed to place order",
            "error": str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([BearerAuthentication])
def get_orders(request):
    user = request.user
    role_code = (user.role.role_code or "").strip().upper()
    if role_code == 'OWN':
        order_ids = OrderItem.objects.filter(product__user=user).values_list('order_id', flat=True).distinct()
        qs = Order.objects.filter(order_id__in=order_ids)
    else:
        # Customer's own orders
        qs = Order.objects.filter(customer=user)

    qs = qs.select_related('customer', 'owner').prefetch_related('items', 'items__product').order_by('-placed_at')

    data = []
    for order in qs:
        data.append({
            "order_id": order.order_id,
            "customer": {
                "u_id": order.customer.u_id,
                "name": order.customer.name,
                "number": order.customer.number,
            },
            "owner": {
                "u_id": order.owner.u_id,
                "name": order.owner.name,
                "number": order.owner.number,
            },
            "customer_name": order.customer_name,
            "phone_number": order.phone_number,
            "address_line": order.address_line,
            "city": order.city,
            "state": order.state,
            "pincode": order.pincode,
            "landmark": order.landmark,
            "items": [
                {
                    "product_id": it.product.product_id if it.product else None,
                    "product_name": it.product_name,
                    "product_price": str(it.product_price),
                    "quantity": it.quantity,
                    "total_price": str(it.total_price),
                }
                for it in order.items.all()
            ],
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "delivery_charge": str(order.delivery_charge),
            "total_amount": str(order.total_amount),
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "status": order.status,
            "placed_at": order.placed_at,
            "updated_at": order.updated_at,
        })

    return Response({
        "status": True,
        "message": "Orders fetched successfully",
        "count": len(data),
        "data": data,
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'POST'])
@authentication_classes([BearerAuthentication])
def update_order_status(request, order_id):
    
    owner = request.user
    role_code = (owner.role.role_code or "").strip().upper()
    if role_code != "OWN":
        return Response({
            "status": False,
            "message": "Only service center owners can update order status"
        }, status=status.HTTP_403_FORBIDDEN)
    new_status = (request.data.get('status') or '').strip().lower()
    ALLOWED = [
        'pending',
        'confirmed',
        'processing',
        'shipped',
        'delivered',
        'cancelled',
    ]
    if new_status not in ALLOWED:
        return Response({
            "status": False,
            "message": f"Invalid status. Allowed: {', '.join(ALLOWED)}"
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        order = Order.objects.select_related('customer', 'owner').get(
            order_id=order_id,
            owner=owner,
        )
    except Order.DoesNotExist:
        return Response({
            "status": False,
            "message": "Order not found"
        }, status=status.HTTP_404_NOT_FOUND)
    order.status = new_status
    order.save(update_fields=['status', 'updated_at'])
    try:
        save_notification(
            order.customer.u_id,
            f"Order #{order.order_id} is now {new_status}",
            "Order Notification",
        )
    except Exception as e:
        print("ORDER STATUS NOTIF ERROR:", repr(e))
    return Response({
        "status": True,
        "message": f"Order marked {new_status}",
        "data": {
            "order_id": order.order_id,
            "status": order.status,
            "updated_at": order.updated_at,
        }
    }, status=status.HTTP_200_OK)