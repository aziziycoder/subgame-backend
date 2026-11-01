import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


def generate_user_id():
    return uuid.uuid4().hex[:28]


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email kiritilishi shart!')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser is_staff=True bo‘lishi kerak.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser is_superuser=True bo‘lishi kerak.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('user', 'Foydalanuvchi'),
        ('admin', 'Administrator'),
    )

    id = models.CharField(max_length=128, primary_key=True, default=generate_user_id)
    email = models.EmailField(unique=True, db_index=True)
    display_name = models.CharField(max_length=255, blank=True, default='')
    photo_url = models.URLField(max_length=1000, blank=True, default='')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'subgame_users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.display_name or 'Noma’lum'})"

    @property
    def is_admin(self):
        return self.role == 'admin' or self.is_superuser
