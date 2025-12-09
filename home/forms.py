from django import forms
from django.contrib.auth.models import User
from PIL import Image
from .models import UserProfile


class UserUpdateForm(forms.ModelForm):
    """Form for updating User information"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last name'
            }),
        }


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating UserProfile information"""
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'id': 'id_profile_picture_input'
        }),
        help_text="Upload a profile picture (minimum 200x200px, will be cropped to square)"
    )

    class Meta:
        model = UserProfile
        fields = ['bio', 'location', 'favorite_celestial_body', 'profile_picture']
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Tell us about yourself...'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your location'
            }),
            'favorite_celestial_body': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Mars, Jupiter, Andromeda Galaxy'
            }),
        }

    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            # Check if it's a new file upload (not just existing)
            if hasattr(profile_picture, 'read'):
                try:
                    # Open image to check dimensions
                    img = Image.open(profile_picture)
                    width, height = img.size

                    # Validate minimum size
                    if width < 200 or height < 200:
                        raise forms.ValidationError(
                            f"Image must be at least 200x200 pixels. Your image is {width}x{height} pixels."
                        )

                    # Reset file pointer for saving
                    profile_picture.seek(0)
                except Exception as e:
                    if isinstance(e, forms.ValidationError):
                        raise
                    raise forms.ValidationError("Invalid image file. Please upload a valid image.")

        return profile_picture
