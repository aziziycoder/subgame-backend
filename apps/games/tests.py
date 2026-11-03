import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from .models import Game, Slider


class AdminTestBase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='admin@example.com', id='adminuid', role='admin')
        self.user = User.objects.create_user(email='user@example.com', id='uid')

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')


class GameWriteTests(AdminTestBase):
    def test_blank_optional_fields_and_relative_images_are_accepted(self):
        self.auth(self.admin)
        response = self.client.post('/api/v1/games/admin/manage/', {
            'id': 'new-game', 'slug': 'new-game', 'title': 'New', 'cover': '/images/new.jpg',
            'cardImage': '', 'heroImage': '', 'subtitleVersion': '', 'price': '',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_update_cannot_change_the_primary_key(self):
        Game.objects.create(id='g', slug='g', title='G', cover='https://x/y.jpg')
        self.auth(self.admin)
        response = self.client.put('/api/v1/games/admin/manage/g/', {'id': 'other', 'title': 'Changed'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(Game.objects.get(id='g').title, 'Changed')


class SliderTests(AdminTestBase):
    payload = {
        'id': 's1', 'slug': 's1', 'title': 'T', 'headlinePrefix': 'P', 'bgImage': '/images/bg.jpg',
        'cardImage': '', 'order': 2, 'isActive': False,
    }

    def test_admin_crud_uses_camel_case(self):
        self.auth(self.admin)
        created = self.client.post('/api/v1/games/admin/sliders/', self.payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['headlinePrefix'], 'P')

        updated = self.client.put('/api/v1/games/admin/sliders/s1/', {'isActive': True}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertTrue(Slider.objects.get(id='s1').is_active)

        self.assertEqual(self.client.delete('/api/v1/games/admin/sliders/s1/').status_code, 204)

    def test_public_list_hides_inactive_and_admin_list_shows_them(self):
        Slider.objects.create(id='off', slug='off', title='Off', bg_image='/a.jpg', is_active=False)
        self.assertEqual(self.client.get('/api/v1/games/sliders/').data, [])
        self.auth(self.admin)
        self.assertEqual(len(self.client.get('/api/v1/games/admin/sliders/').data), 1)

    def test_writes_require_admin(self):
        self.auth(self.user)
        self.assertEqual(self.client.post('/api/v1/games/admin/sliders/', self.payload, format='json').status_code, 403)


class UploadTests(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, PUBLIC_API_URL='https://api.example.com')
        override.enable()
        self.addCleanup(override.disable)

    def upload(self, name):
        return self.client.post('/api/v1/games/admin/upload/', {
            'file': SimpleUploadedFile(name, b'data'), 'folder': 'stray',
        }, format='multipart')

    def test_admin_upload_returns_public_url(self):
        self.auth(self.admin)
        response = self.upload('sub.pak')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['url'].startswith('https://api.example.com/media/uploads/stray/'))
        self.assertTrue(response.data['url'].endswith('/sub.pak'))
        self.assertEqual(response.data['size'], 4)

    def test_path_traversal_stays_inside_media(self):
        self.auth(self.admin)
        response = self.upload('../../evil.pak')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('..', response.data['url'])

    def test_executable_web_files_are_blocked(self):
        self.auth(self.admin)
        self.assertEqual(self.upload('page.html').status_code, 400)

    def test_requires_admin(self):
        self.auth(self.user)
        self.assertEqual(self.upload('sub.pak').status_code, 403)
