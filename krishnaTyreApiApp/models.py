from django.db import models

class Role(models.Model):
    role_id = models.AutoField(primary_key=True)
    role_name = models.CharField(max_length=100, unique=True)
    role_code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"

    def __str__(self):
        return self.role_name

class User(models.Model):
    u_id = models.AutoField(primary_key=True)
    role = models.ForeignKey( Role,on_delete=models.PROTECT,related_name="users")
    name = models.CharField(max_length=150)
    number = models.CharField(max_length=15, unique=True)
    subscribed = models.BooleanField(default=False)
    mpin = models.CharField(max_length=255)
    profile_image_url = models.URLField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    shop_open = models.BooleanField(default=True,help_text="Whether the shop is currently open and accepting bookings.")
    emergency_service = models.BooleanField(default=False,help_text="Whether this owner offers 24/7 emergency roadside service."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.name


class Notification(models.Model):
    notification_id = models.AutoField(primary_key=True)
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

class Category(models.Model):
    category_id = models.AutoField(primary_key=True)
    category_name = models.CharField( max_length=150, unique=True)
    category_code = models.CharField( max_length=50, unique=True)
    description = models.TextField( blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "categories"

    def __str__(self):
        return self.category_name


class Service(models.Model):
    service_id = models.AutoField(primary_key=True)
    service_name = models.CharField(max_length=150, unique=True)
    service_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField( blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "services"

    def __str__(self):
        return self.service_name

class Products(models.Model):
    product_id = models.AutoField(primary_key=True)
    user = models.ForeignKey( User,on_delete=models.CASCADE,related_name='products', db_column='u_id')
    product_name = models.CharField(max_length=255)
    product_price = models.DecimalField(max_digits=10,decimal_places=2)
    stock_number = models.IntegerField(default=0)
    category = models.CharField(max_length=150)
    is_available = models.BooleanField(default=True)
    brand_name = models.CharField(max_length=150)
    vehicle_name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    product_image_url = models.URLField(max_length=500,blank=True,null=True)

    created_at = models.DateTimeField( auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"

    def __str__(self):
        return self.product_name


class Appointments(models.Model):

    appointment_id = models.AutoField(primary_key=True)
    service_center = models.ForeignKey(User, on_delete=models.CASCADE,related_name='service_center_appointments',db_column='service_center_u_id')
    customer = models.ForeignKey( User, on_delete=models.CASCADE, related_name='customer_appointments', db_column='customer_u_id')
    vehicle_model = models.CharField(max_length=150)
    vehicle_number = models.CharField(max_length=50)
    service_type = models.CharField(max_length=150)
    description = models.TextField(blank=True,null=True)
    estimated_cost = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    status = models.CharField(max_length=30,default='pending')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "appointments"

    def __str__(self):
        return f"Appointment {self.appointment_id}"
        

class EmergencyAppointments(models.Model):
    emergency_id = models.AutoField(primary_key=True)
    service_center = models.ForeignKey(User,on_delete=models.CASCADE,related_name='emergency_service_center_appointments',db_column='service_center_u_id')
    customer = models.ForeignKey(User,on_delete=models.CASCADE,related_name='customer_emergency_appointments',db_column='customer_u_id')
    vehicle_model = models.CharField(max_length=255)
    vehicle_number = models.CharField(max_length=100)
    description = models.TextField(blank=True,null=True)
    location = models.CharField(max_length=500)
    issue_photo_urls = models.JSONField(blank=True,null=True)
    status = models.CharField(max_length=50,default='pending')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "emergency_appointments"

    def __str__(self):
        return f"Emergency #{self.emergency_id}"


class GeneratedBills(models.Model):
    bill_id = models.AutoField(primary_key=True)
    owner = models.ForeignKey( User,on_delete=models.CASCADE,related_name='generated_bills',db_column='owner_u_id')
    customer = models.ForeignKey(User,on_delete=models.CASCADE,related_name='customer_bills',db_column='customer_u_id')
    customer_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    vehicle_number = models.CharField(max_length=100)
    subtotal = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    tax_percentage = models.DecimalField(max_digits=5,decimal_places=2,default=10)
    tax_amount = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    total_amount = models.DecimalField( max_digits=12,decimal_places=2,default=0)

    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "generated_bills"

    def __str__(self):
        return f"Bill #{self.bill_id}"


class GeneratedBillServices(models.Model):
    bill_service_id = models.AutoField(primary_key=True)
    bill = models.ForeignKey(GeneratedBills,on_delete=models.CASCADE,related_name='services',db_column='bill_id')
    service_name = models.CharField(max_length=255)
    quantity = models.IntegerField( default=1)
    service_price = models.DecimalField(max_digits=12,decimal_places=2)
    total_price = models.DecimalField(max_digits=12,decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "generated_bill_services"

    def __str__(self):
        return self.service_name


class Order(models.Model):
    order_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(User,on_delete=models.CASCADE,related_name='orders',db_column='u_id',)
    customer_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=15)
    address_line = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=30, default='pending')
    payment_method = models.CharField(max_length=30,default='cod')
    payment_status = models.CharField(max_length=30,default='unpaid')

    owner = models.ForeignKey( User,on_delete=models.SET_NULL,null=True,blank=True,related_name='received_orders',db_column='shop_owner_u_id',)

    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ['-placed_at']

    def __str__(self):
        return f"Order #{self.order_id} by {self.customer_name}"


class OrderItem(models.Model):
    order_item_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='items', db_column='order_id',)
    product = models.ForeignKey(Products,on_delete=models.SET_NULL,null=True,blank=True,related_name='order_items',db_column='product_id',)
    product_name = models.CharField(max_length=255)
    product_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.IntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_items"

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class Kyc(models.Model):
    kyc_id = models.AutoField(primary_key=True)
    u_id = models.ForeignKey(User,on_delete=models.CASCADE,related_name='kyc',db_column='u_id',)
    aadhaar_number = models.CharField(max_length=12, unique=True)
    pan_number = models.CharField(max_length=10, unique=True)
    gst_number = models.CharField(max_length=15,blank=True,null=True,)
    status = models.CharField(max_length=20,default='pending', help_text='pending | verified | rejected',)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kyc'
        indexes = [
            models.Index(fields=['u_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'KYC #{self.kyc_id} — {self.u_id.name}'


class Subscription(models.Model):
    """
    Stores Premium subscription records for users.
    One user can have multiple subscription history rows, but only one active at a time.
    """

    PLAN_CHOICES = [
        # Bike
        ('bike_3m', 'Bike - Quarterly'),
        ('bike_6m', 'Bike - Half Yearly'),
        ('bike_1y', 'Bike - Yearly'),
        # Auto
        ('auto_3m', 'Auto - Quarterly'),
        ('auto_6m', 'Auto - Half Yearly'),
        ('auto_1y', 'Auto - Yearly'),
        # Car
        ('car_3m', 'Car - Quarterly'),
        ('car_6m', 'Car - Half Yearly'),
        ('car_1y', 'Car - Yearly'),
        # Van
        ('van_3m', 'Van - Quarterly'),
        ('van_6m', 'Van - Half Yearly'),
        ('van_1y', 'Van - Yearly'),
        # Truck
        ('truck_3m', 'Truck - Quarterly'),
        ('truck_6m', 'Truck - Half Yearly'),
        ('truck_1y', 'Truck - Yearly'),
        # Container
        ('container_3m', 'Container - Quarterly'),
        ('container_6m', 'Container - Half Yearly'),
        ('container_1y', 'Container - Yearly'),
    ]

    VEHICLE_CHOICES = [
        ('bike', 'Bike'),
        ('auto', 'Auto / 3-Wheeler'),
        ('car', 'Car'),
        ('van', 'Van'),
        ('truck', 'Truck'),
        ('container', 'Container Truck'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]

    subscription_id = models.AutoField(primary_key=True)

    u_id = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        db_column='u_id',
    )

    # Plan details
    plan_id = models.CharField(
        max_length=30,
        choices=PLAN_CHOICES,
        help_text='Plan identifier (e.g. car_6m)',
    )
    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_CHOICES,
        help_text='Vehicle category',
    )
    plan_title = models.CharField(
        max_length=50,
        help_text='Display name (Quarterly / Half Yearly / Yearly)',
    )

    # Amounts (store in paise to avoid float issues, matching Razorpay)
    amount_paise = models.IntegerField(
        help_text='Amount in paise (e.g. 109900 = ₹1099)',
    )
    currency = models.CharField(
        max_length=10,
        default='INR',
    )
    duration_days = models.IntegerField(
        help_text='Plan duration in days',
    )

    # Payment tracking (Razorpay)
    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
    )
    razorpay_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    payment_method = models.CharField(
        max_length=30,
        default='razorpay',
        help_text='razorpay | manual | upi',
    )

    # Subscription lifecycle
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
    )
    started_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Set when subscription becomes active',
    )
    expires_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Calculated from started_at + duration_days',
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        indexes = [
            models.Index(fields=['u_id', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return (
            f'SUB #{self.subscription_id} — '
            f'{self.u_id.name} — {self.plan_id} — {self.status}'
        )