"""
Tests for the AI Chatbot Widget feature
"""
import json
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock


class ChatbotAPITests(TestCase):
    """Tests for the chatbot API endpoint"""

    def setUp(self):
        self.client = Client()

    def test_chatbot_api_get_method_not_allowed(self):
        """Test that GET requests to chatbot API are not allowed"""
        response = self.client.get(reverse('chatbot_api'))
        self.assertEqual(response.status_code, 405)
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_chatbot_api_empty_message(self):
        """Test that empty messages are rejected"""
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({'message': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Message cannot be empty')

    def test_chatbot_api_whitespace_only_message(self):
        """Test that whitespace-only messages are rejected"""
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({'message': '   '}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)

    @patch('home.views.OpenAI')
    @patch('home.views.OPENAI_API_KEY', 'test-key')
    def test_chatbot_api_successful_response(self, mock_openai):
        """Test successful chatbot response"""
        # Mock OpenAI response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Auroras are caused by solar wind particles interacting with Earth's atmosphere."
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # Make request
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({
                'message': 'What causes auroras?',
                'history': []
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        self.assertIn('response', data)
        self.assertIn('Auroras are caused by solar wind', data['response'])

        # Verify OpenAI was called correctly
        mock_openai.assert_called_once_with(api_key='test-key')
        mock_client.chat.completions.create.assert_called_once()

    @patch('home.views.OpenAI')
    @patch('home.views.OPENAI_API_KEY', 'test-key')
    def test_chatbot_api_with_conversation_history(self, mock_openai):
        """Test chatbot maintains conversation context"""
        # Mock OpenAI response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "They can appear in green, red, pink, yellow, blue, and purple."
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # Make request with conversation history
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({
                'message': 'What colors can they be?',
                'history': [
                    {'role': 'user', 'content': 'What causes auroras?'},
                    {'role': 'assistant', 'content': 'Auroras are caused by solar wind...'}
                ]
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))

        # Verify history was passed to OpenAI
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']

        # Should have: system message + 2 history messages + new message
        self.assertGreaterEqual(len(messages), 4)
        self.assertEqual(messages[0]['role'], 'system')

    def test_chatbot_api_invalid_json(self):
        """Test that invalid JSON is rejected"""
        response = self.client.post(
            reverse('chatbot_api'),
            data='invalid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)

    @patch('home.views.OPENAI_API_KEY', None)
    def test_chatbot_api_missing_api_key(self):
        """Test error when OpenAI API key is not configured"""
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({
                'message': 'Test message',
                'history': []
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertIn('API key not configured', data['error'])

    @patch('home.views.OpenAI')
    @patch('home.views.OPENAI_API_KEY', 'test-key')
    def test_chatbot_api_openai_error(self, mock_openai):
        """Test handling of OpenAI API errors"""
        # Mock OpenAI to raise an exception
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception('OpenAI API error')
        mock_openai.return_value = mock_client

        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({
                'message': 'What causes auroras?',
                'history': []
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertIn('error', data)

    @patch('home.views.OpenAI')
    @patch('home.views.OPENAI_API_KEY', 'test-key')
    def test_chatbot_api_request_parameters(self, mock_openai):
        """Test that correct parameters are sent to OpenAI"""
        # Mock OpenAI response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Test response"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # Make request
        response = self.client.post(
            reverse('chatbot_api'),
            data=json.dumps({
                'message': 'Test question',
                'history': []
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify OpenAI was called with correct parameters
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs['model'], 'gpt-4o-mini')
        self.assertEqual(call_args.kwargs['max_tokens'], 500)
        self.assertEqual(call_args.kwargs['temperature'], 0.7)

        # Verify system message is present
        messages = call_args.kwargs['messages']
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('astronomy', messages[0]['content'].lower())