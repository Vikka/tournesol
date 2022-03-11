from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.tests.factories.user import UserFactory
from tournesol.models.poll import Poll
from tournesol.tests.factories.comparison import ComparisonFactory
from tournesol.tests.factories.entity import VideoFactory


class SimpleAllConnectedTest(TestCase):
    """
    TestCase for the unconnected entities API.
    """
    def setUp(self):
        self.client = APIClient()
        self.user_1 = UserFactory()
        self.poll_videos = Poll.default_poll()
        self.user_base_url = "/users/me/unconnected_entities/{}".format(
            self.poll_videos.name
        )

        video_1 = VideoFactory()
        video_2 = VideoFactory()
        video_3 = VideoFactory()

        self.video_source = video_1

        ComparisonFactory(
            user=self.user_1,
            entity_1=video_1,
            entity_2=video_2,
        )
        ComparisonFactory(
            user=self.user_1,
            entity_1=video_1,
            entity_2=video_3,
        )
        ComparisonFactory(
            user=self.user_1,
            entity_1=video_2,
            entity_2=video_3,
        )

    def test_not_authenticated_cannot_show_unconnected_entities(self):
        response = self.client.get(
            "{}/{}/".format(self.user_base_url, self.video_source.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_all_connected_video_shouldnt_return_entities(self):
        self.client.force_authenticate(self.user_1)

        response = self.client.get(
            "{}/{}/".format(self.user_base_url, self.video_source.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class AdvancedAllConnectedTest(TestCase):
    """
    TestCase for the unconnected entities API.
    """
    def setUp(self):
        self.client = APIClient()
        self.user_1 = UserFactory()
        self.poll_videos = Poll.default_poll()
        self.user_base_url = "/users/me/unconnected_entities/{}".format(
            self.poll_videos.name
        )

        video_4 = VideoFactory()
        video_3 = VideoFactory()
        video_2 = VideoFactory()
        video_1 = VideoFactory()

        self.video_source = video_1

        ComparisonFactory(
            user=self.user_1,
            entity_1=video_3,
            entity_2=video_4,
        )
        ComparisonFactory(
            user=self.user_1,
            entity_1=video_2,
            entity_2=video_3,
        )
        ComparisonFactory(
            user=self.user_1,
            entity_1=video_1,
            entity_2=video_3,
        )

    def test_all_linked_should_return_empty(self):
        self.client.force_authenticate(self.user_1)

        response = self.client.get(
            "{}/{}/".format(self.user_base_url, self.video_source.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)