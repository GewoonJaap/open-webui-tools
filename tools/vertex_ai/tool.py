"""
title: Vertex AI Media Generator
author: Assistant
author_url: https://github.com/open-webui/open-webui-tools
description: A tool that generates images and music using Google Cloud Vertex AI (Imagen and Lyria) with automatic upload to asset proxy.
requirements: google-auth, google-cloud-aiplatform, requests
version: 0.7.2
license: MIT
"""

import unittest
from typing import Any, Callable
import json
import base64
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import requests
from pydantic import BaseModel, Field


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )

    async def emit_image(self, image_url, caption="Generated Image"):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "message",
                    "data": {"content": f"![{caption}]({image_url}) \n"},
                }
            )

    async def emit_audio(self, audio_url, caption="Generated Audio"):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "message",
                    "data": {"content": f"<audio>\n{audio_url}\n</audio>\n"},
                }
            )


class Tools:
    # Available Imagen models
    AVAILABLE_IMAGE_MODELS = {
        "imagen-4.0-generate-preview-05-20": "Imagen 4.0 Generate (Preview) - Latest model with advanced capabilities",
        "imagen-4.0-ultra-generate-exp-05-20": "Imagen 4.0 Ultra Generate (Experimental) - Ultra high quality experimental model",
        "imagen-3.0-generate-002": "Imagen 3.0 Generate - Stable production model with good quality",
        "imagen-3.0-fast-generate-001": "Imagen 3.0 Fast Generate - Faster generation with good quality"
    }

    # Available Lyria models
    AVAILABLE_MUSIC_MODELS = {
        "lyria-002": "Lyria 002 - Text-to-music generation with high quality orchestral and instrumental capabilities"
    }
    
    class Valves(BaseModel):
        CITATION: bool = Field(default=True, description="True or false for citation")
        GLOBAL_SERVICE_ACCOUNT_JSON: str = Field(
            default="",
            description="Global Google Cloud Service Account JSON string for Vertex AI authentication.",
        )
        DEFAULT_PROJECT_ID: str = Field(
            default="",
            description="Default Google Cloud Project ID for Vertex AI operations.",
        )
        DEFAULT_LOCATION: str = Field(
            default="us-central1",
            description="Default location/region for Vertex AI operations.",
        )
        DEFAULT_IMAGE_MODEL: str = Field(
            default="imagen-4.0-generate-preview-05-20",
            description="Default Imagen model to use for image generation.",
        )
        DEFAULT_MUSIC_MODEL: str = Field(
            default="lyria-002",
            description="Default Lyria model to use for music generation.",
        )
        ASSET_PROXY_URL: str = Field(
            default="https://ai-asset-proxy.mrproper.dev/api/upload",
            description="Asset proxy URL for uploading generated media.",
        )
        ASSET_PROXY_AUTH_GUID: str = Field(
            default="",
            description="Authentication GUID for the asset proxy.",
        )
        AUTO_UPLOAD_MEDIA: bool = Field(
            default=True,
            description="Automatically upload generated media to asset proxy.",
        )

    class UserValves(BaseModel):
        SERVICE_ACCOUNT_JSON: str = Field(
            default="",
            description="(Optional) User-specific Google Cloud Service Account JSON. If provided, overrides the global service account.",
        )
        PROJECT_ID: str = Field(
            default="",
            description="(Optional) User-specific Google Cloud Project ID. If provided, overrides the default project ID.",
        )
        LOCATION: str = Field(
            default="",
            description="(Optional) User-specific location/region. If provided, overrides the default location.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation = self.valves.CITATION
        self._cached_credentials = None
        self._cached_token = None
        self._token_expiry = None

    def _get_credentials_from_json(self, service_account_json: str):
        """Parse service account JSON and create credentials object."""
        try:
            if not service_account_json.strip():
                raise ValueError("Service account JSON is empty")
            
            # Try to parse the JSON
            service_account_info = json.loads(service_account_json)
            
            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            for field in required_fields:
                if field not in service_account_info:
                    raise ValueError(f"Missing required field in service account JSON: {field}")
            
            # Create credentials with the required scopes for Vertex AI
            scopes = [
                'https://www.googleapis.com/auth/cloud-platform'
            ]
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=scopes
            )
            
            return credentials, service_account_info.get('project_id')
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in service account: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to create credentials: {str(e)}")

    def _is_token_valid(self):
        """Check if the current token is still valid."""
        if not self._cached_token or not self._token_expiry:
            return False
        
        # Add 5 minutes buffer before expiry
        buffer_time = timedelta(minutes=5)
        return datetime.utcnow() < (self._token_expiry - buffer_time)

    async def _refresh_token(self, emitter):
        """Refresh the access token."""
        try:
            if not self._cached_credentials:
                raise ValueError("No cached credentials available")
            
            # Create a new request object
            request = Request()
            
            # Refresh the credentials to get a new token
            self._cached_credentials.refresh(request)
            
            # Extract the token and expiry
            if hasattr(self._cached_credentials, 'token') and self._cached_credentials.token:
                self._cached_token = self._cached_credentials.token
                self._token_expiry = self._cached_credentials.expiry
                return True
            else:
                raise ValueError("Failed to obtain access token from credentials")
                
        except Exception as e:
            await emitter.error_update(f"Token refresh failed: {str(e)}")
            return False

    async def _ensure_authenticated(self, emitter, __user__):
        """Ensure we have a valid authentication token."""
        if not self._is_token_valid():
            await emitter.progress_update("Setting up Vertex AI authentication...")
            
            # Initialize UserValves if not present
            if "valves" not in __user__:
                __user__["valves"] = self.UserValves()
            
            # Get user valves or create from dict if needed
            user_valves = __user__["valves"]
            if not isinstance(user_valves, self.UserValves) and isinstance(user_valves, dict):
                try:
                    user_valves = self.UserValves(**user_valves)
                except Exception as e:
                    await emitter.progress_update(f"Warning: Failed to parse user valves: {e}. Using defaults.")
                    user_valves = self.UserValves()

            # Determine which service account JSON to use
            service_account_json = (
                user_valves.SERVICE_ACCOUNT_JSON or 
                self.valves.GLOBAL_SERVICE_ACCOUNT_JSON
            )
            
            if not service_account_json:
                raise ValueError("No service account JSON provided. Please configure authentication credentials in the tool settings.")
            
            # Parse credentials
            credentials, sa_project_id = self._get_credentials_from_json(service_account_json)
            self._cached_credentials = credentials
            
            # Get fresh token
            success = await self._refresh_token(emitter)
            if not success:
                raise ValueError("Failed to obtain access token")
            
            await emitter.progress_update("Authentication successful")
            return user_valves, sa_project_id
        
        return None, None

    async def _upload_to_asset_proxy(self, emitter, base64_data, mime_type):
        """Upload base64 media data to the asset proxy."""
        upload_details = {
            'success': False,
            'upload_id': None,
            'access_url': None,
            'error': None,
            'status_code': None,
            'response_text': None,
            'request_details': None
        }
        
        try:
            await emitter.progress_update("Uploading media to asset proxy...")
            
            headers = {
                'X-Auth-Guid': self.valves.ASSET_PROXY_AUTH_GUID,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'data': base64_data,
                'mimeType': mime_type
            }
            
            # Store request details for debugging
            upload_details['request_details'] = {
                'url': self.valves.ASSET_PROXY_URL,
                'headers': {k: v for k, v in headers.items() if k != 'X-Auth-Guid'},  # Don't log auth
                'payload_keys': list(payload.keys()),
                'data_length': len(base64_data),
                'mime_type': mime_type
            }
            
            response = requests.post(
                self.valves.ASSET_PROXY_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            upload_details['status_code'] = response.status_code
            upload_details['response_text'] = response.text
            
            # Accept both 200 and 201 as successful responses
            if response.status_code in [200, 201]:
                try:
                    upload_result = response.json()
                    upload_details['upload_id'] = upload_result.get('id')
                    
                    if upload_details['upload_id']:
                        upload_details['access_url'] = f"https://ai-asset-proxy.mrproper.dev/api/upload/{upload_details['upload_id']}"
                        upload_details['success'] = True
                        await emitter.progress_update("Media uploaded successfully")
                    else:
                        upload_details['error'] = "Upload successful but no ID returned in response"
                except json.JSONDecodeError as e:
                    upload_details['error'] = f"Failed to parse JSON response: {str(e)}"
            else:
                upload_details['error'] = f"HTTP {response.status_code}: {response.text}"
                
        except requests.exceptions.Timeout:
            upload_details['error'] = "Upload request timed out after 30 seconds"
        except requests.exceptions.ConnectionError as e:
            upload_details['error'] = f"Connection error: {str(e)}"
        except requests.exceptions.RequestException as e:
            upload_details['error'] = f"Request error: {str(e)}"
        except Exception as e:
            upload_details['error'] = f"Unexpected error: {str(e)}"
        
        if not upload_details['success']:
            await emitter.progress_update(f"Upload failed: {upload_details['error']}")
        
        return upload_details

    async def list_available_models(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Lists all available models for image and music generation.
        
        :return: List of available models with descriptions
        """
        emitter = EventEmitter(__event_emitter__)
        
        try:
            await emitter.progress_update("Retrieving available models...")
            
            result_parts = ["Available Vertex AI Models:"]
            result_parts.append("")
            
            # Image models
            result_parts.append(f"Image Generation Models ({len(self.AVAILABLE_IMAGE_MODELS)} total):")
            result_parts.append("")
            for model_id, description in self.AVAILABLE_IMAGE_MODELS.items():
                is_default = " (DEFAULT)" if model_id == self.valves.DEFAULT_IMAGE_MODEL else ""
                result_parts.append(f"Model: {model_id}{is_default}")
                result_parts.append(f"Description: {description}")
                result_parts.append("")
            
            # Music models
            result_parts.append(f"Music Generation Models ({len(self.AVAILABLE_MUSIC_MODELS)} total):")
            result_parts.append("")
            for model_id, description in self.AVAILABLE_MUSIC_MODELS.items():
                is_default = " (DEFAULT)" if model_id == self.valves.DEFAULT_MUSIC_MODEL else ""
                result_parts.append(f"Model: {model_id}{is_default}")
                result_parts.append(f"Description: {description}")
                result_parts.append("")
            
            result_parts.append("Usage:")
            result_parts.append("For images: generate_image('your prompt', model='model_name')")
            result_parts.append("For music: generate_music('your prompt', model='model_name')")
            
            result = "\n".join(result_parts)
            
            await emitter.success_update("Model list retrieved successfully!")
            return result
            
        except Exception as e:
            error_message = f"Failed to retrieve model list: {str(e)}"
            await emitter.error_update(error_message)
            return error_message

    async def generate_image(
        self,
        prompt: str,
        model: str = None,
        aspect_ratio: str = "1:1",
        sample_count: int = 1,
        enhance_prompt: bool = True,
        person_generation: str = "allow_all",
        add_watermark: bool = False,
        include_rai_reason: bool = True,
        language: str = "auto",
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Generates an image using Google's Imagen API on Vertex AI and optionally uploads to asset proxy.
        
        :param prompt: The text prompt for image generation
        :param model: Imagen model to use (if not specified, uses default model)
        :param aspect_ratio: Image aspect ratio (1:1, 9:16, 16:9, 4:3, 3:4)
        :param sample_count: Number of images to generate (1-4)
        :param enhance_prompt: Whether to enhance the prompt automatically
        :param person_generation: Person generation policy (allow_all, allow_adult, block_some, block_most)
        :param add_watermark: Whether to add a watermark to the generated image
        :param include_rai_reason: Whether to include responsible AI reasoning
        :param language: Language for prompt processing (auto, en, etc.)
        :return: Generated image information with URLs or error message
        """
        emitter = EventEmitter(__event_emitter__)
        
        try:
            await emitter.progress_update(f"Starting image generation for: {prompt[:50]}...")
            
            # Determine which model to use
            selected_model = model or self.valves.DEFAULT_IMAGE_MODEL
            
            # Validate the model
            if selected_model not in self.AVAILABLE_IMAGE_MODELS:
                available_models = ", ".join(self.AVAILABLE_IMAGE_MODELS.keys())
                raise ValueError(f"Invalid image model '{selected_model}'. Available models: {available_models}")
            
            await emitter.progress_update(f"Using model: {selected_model}")
            
            # Ensure we're authenticated (happens automatically)
            user_valves, sa_project_id = await self._ensure_authenticated(emitter, __user__)
            
            if user_valves is None:
                # Already authenticated, get user valves
                if "valves" not in __user__:
                    __user__["valves"] = self.UserValves()
                
                user_valves = __user__["valves"]
                if not isinstance(user_valves, self.UserValves) and isinstance(user_valves, dict):
                    user_valves = self.UserValves(**user_valves)
            
            # Determine project ID and location
            project_id = (
                user_valves.PROJECT_ID or 
                self.valves.DEFAULT_PROJECT_ID or 
                sa_project_id
            )
            
            location = (
                user_valves.LOCATION or 
                self.valves.DEFAULT_LOCATION
            )
            
            if not project_id:
                raise ValueError("No project ID available. Please specify project ID in settings or ensure it's included in the service account JSON.")
            
            # Validate parameters
            valid_aspect_ratios = ["1:1", "9:16", "16:9", "4:3", "3:4"]
            if aspect_ratio not in valid_aspect_ratios:
                aspect_ratio = "1:1"
                await emitter.progress_update(f"Invalid aspect ratio, using 1:1")
            
            if sample_count < 1 or sample_count > 4:
                sample_count = 1
                await emitter.progress_update(f"Invalid sample count, using 1")
            
            valid_person_generation = ["allow_all", "allow_adult", "block_some", "block_most"]
            if person_generation not in valid_person_generation:
                person_generation = "allow_all"
                await emitter.progress_update(f"Invalid person generation policy, using allow_all")
            
            await emitter.progress_update("Preparing image generation request...")
            
            # Prepare the API request
            url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{selected_model}:predict"
            
            headers = {
                'Authorization': f'Bearer {self._cached_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "instances": [
                    {
                        "prompt": prompt
                    }
                ],
                "parameters": {
                    "aspectRatio": aspect_ratio,
                    "sampleCount": sample_count,
                    "enhancePrompt": enhance_prompt,
                    "personGeneration": person_generation,
                    "addWatermark": add_watermark,
                    "includeRaiReason": include_rai_reason,
                    "language": language
                }
            }
            
            await emitter.progress_update("Sending request to Imagen API...")
            
            # Make the API request
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                response_data = response.json()
                
                await emitter.progress_update("Processing generated images...")
                
                # Parse the response
                predictions = response_data.get('predictions', [])
                
                if not predictions:
                    raise ValueError("No images generated in response")
                
                result_parts = [f"Image Generation Successful!"]
                result_parts.append(f"Prompt: {prompt}")
                result_parts.append(f"Model: {selected_model}")
                result_parts.append(f"Parameters: {aspect_ratio}, {sample_count} image(s)")
                result_parts.append("")
                
                generated_images = []  # Track successful images for rendering
                
                for i, prediction in enumerate(predictions):
                    result_parts.append(f"Image {i + 1}:")
                    
                    # Extract image data
                    if 'bytesBase64Encoded' in prediction:
                        image_data = prediction['bytesBase64Encoded']
                        mime_type = prediction.get('mimeType', 'image/png')
                        
                        result_parts.append(f"- Format: {mime_type}")
                        result_parts.append(f"- Size: {len(image_data)} characters (base64)")
                        
                        # Upload to asset proxy if enabled
                        if self.valves.AUTO_UPLOAD_MEDIA:
                            upload_result = await self._upload_to_asset_proxy(emitter, image_data, mime_type)
                            
                            if upload_result['success']:
                                result_parts.append(f"- Upload: SUCCESS (Status: {upload_result['status_code']})")
                                result_parts.append(f"- Upload ID: {upload_result['upload_id']}")
                                result_parts.append(f"- Access URL: {upload_result['access_url']}")
                                result_parts.append(f"- Direct Link: {upload_result['access_url']}")
                                
                                # Add to successful images for rendering
                                generated_images.append({
                                    'url': upload_result['access_url'],
                                    'caption': f"Generated Image {i + 1} ({selected_model}): {prompt[:50]}..."
                                })
                            else:
                                result_parts.append("- Upload: FAILED")
                                result_parts.append(f"- Upload Error: {upload_result['error']}")
                                result_parts.append(f"- Status Code: {upload_result['status_code']}")
                                result_parts.append(f"- Response: {upload_result['response_text']}")
                                if upload_result['request_details']:
                                    req_details = upload_result['request_details']
                                    result_parts.append(f"- Request URL: {req_details['url']}")
                                    result_parts.append(f"- Data Length: {req_details['data_length']}")
                                    result_parts.append(f"- MIME Type: {req_details['mime_type']}")
                                result_parts.append(f"- Base64 data (first 100 chars): {image_data[:100]}...")
                        else:
                            result_parts.append(f"- Base64 data (first 100 chars): {image_data[:100]}...")
                    
                    # Extract safety information
                    if 'raiFilteredReason' in prediction:
                        result_parts.append(f"- Safety filter: {prediction['raiFilteredReason']}")
                    
                    result_parts.append("")
                
                # Add enhanced prompt if available
                if predictions and 'enhancedPrompt' in predictions[0]:
                    result_parts.append(f"Enhanced Prompt: {predictions[0]['enhancedPrompt']}")
                
                # Render images to the user if any were successfully uploaded
                if generated_images and __event_emitter__:
                    await emitter.progress_update("Rendering images...")
                    for img in generated_images:
                        await emitter.emit_image(img['url'], img['caption'])
                
                result = "\n".join(result_parts)
                
                await emitter.success_update(f"Generated and rendered {len(predictions)} image(s) successfully!")
                return result
                
            else:
                error_data = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_data = error_json['error'].get('message', error_data)
                except:
                    pass
                
                raise ValueError(f"Image generation failed ({response.status_code}): {error_data}")
            
        except Exception as e:
            error_message = f"Image generation failed: {str(e)}"
            
            if "quota" in str(e).lower():
                error_message += "\n\nTroubleshooting:\n- Check your Vertex AI quota limits\n- Ensure billing is enabled for your project"
            elif "403" in str(e) or "permission" in str(e).lower():
                error_message += "\n\nTroubleshooting:\n- Verify service account has Vertex AI permissions\n- Check if Imagen API is enabled in your project"
            elif "400" in str(e):
                error_message += "\n\nTroubleshooting:\n- Check if the prompt meets content policy guidelines\n- Verify all parameters are valid"
            elif "Invalid image model" in str(e):
                error_message += f"\n\nUse 'list_available_models()' to see all available models."
            elif "No service account JSON provided" in str(e):
                error_message += "\n\nTroubleshooting:\n- Configure your service account JSON in the tool settings\n- Ensure the JSON contains all required fields\n- Check that the service account has proper permissions"
            
            await emitter.error_update(error_message)
            return error_message

    async def generate_music(
        self,
        prompt: str,
        model: str = None,
        negative_prompt: str = "",
        seed: int = None,
        sample_count: int = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Generates music using Google's Lyria API on Vertex AI and optionally uploads to asset proxy.
        
        :param prompt: The text prompt for music generation
        :param model: Lyria model to use (if not specified, uses default model)
        :param negative_prompt: What to avoid in the generated music
        :param seed: Random seed for reproducible results (mutually exclusive with sample_count)
        :param sample_count: Number of music samples to generate (mutually exclusive with seed)
        :return: Generated music information with URLs or error message
        """
        emitter = EventEmitter(__event_emitter__)
        
        try:
            await emitter.progress_update(f"Starting music generation for: {prompt[:50]}...")
            
            # Determine which model to use
            selected_model = model or self.valves.DEFAULT_MUSIC_MODEL
            
            # Validate the model
            if selected_model not in self.AVAILABLE_MUSIC_MODELS:
                available_models = ", ".join(self.AVAILABLE_MUSIC_MODELS.keys())
                raise ValueError(f"Invalid music model '{selected_model}'. Available models: {available_models}")
            
            await emitter.progress_update(f"Using model: {selected_model}")
            
            # Ensure we're authenticated (happens automatically)
            user_valves, sa_project_id = await self._ensure_authenticated(emitter, __user__)
            
            if user_valves is None:
                # Already authenticated, get user valves
                if "valves" not in __user__:
                    __user__["valves"] = self.UserValves()
                
                user_valves = __user__["valves"]
                if not isinstance(user_valves, self.UserValves) and isinstance(user_valves, dict):
                    user_valves = self.UserValves(**user_valves)
            
            # Determine project ID and location
            project_id = (
                user_valves.PROJECT_ID or 
                self.valves.DEFAULT_PROJECT_ID or 
                sa_project_id
            )
            
            location = (
                user_valves.LOCATION or 
                self.valves.DEFAULT_LOCATION
            )
            
            if not project_id:
                raise ValueError("No project ID available. Please specify project ID in settings or ensure it's included in the service account JSON.")
            
            # Validate parameters - seed and sample_count are mutually exclusive
            if seed is not None and sample_count is not None:
                raise ValueError("Cannot specify both seed and sample_count. Use one or the other.")
            
            # Default to sample_count=1 if neither is specified
            if seed is None and sample_count is None:
                sample_count = 1
            
            await emitter.progress_update("Preparing music generation request...")
            
            # Prepare the API request
            url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{selected_model}:predict"
            
            headers = {
                'Authorization': f'Bearer {self._cached_token}',
                'Content-Type': 'application/json'
            }
            
            # Build instance data
            instance = {"prompt": prompt}
            if negative_prompt:
                instance["negative_prompt"] = negative_prompt
            if seed is not None:
                instance["seed"] = seed
            
            # Build parameters
            parameters = {}
            if sample_count is not None:
                parameters["sample_count"] = sample_count
            
            payload = {
                "instances": [instance]
            }
            
            if parameters:
                payload["parameters"] = parameters
            
            await emitter.progress_update("Sending request to Lyria API...")
            
            # Make the API request (music generation can take longer)
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            
            if response.status_code == 200:
                response_data = response.json()
                
                await emitter.progress_update("Processing generated music...")
                
                # Parse the response
                predictions = response_data.get('predictions', [])
                
                if not predictions:
                    raise ValueError("No music generated in response")
                
                result_parts = [f"Music Generation Successful!"]
                result_parts.append(f"Prompt: {prompt}")
                if negative_prompt:
                    result_parts.append(f"Negative Prompt: {negative_prompt}")
                result_parts.append(f"Model: {selected_model}")
                if seed is not None:
                    result_parts.append(f"Seed: {seed}")
                if sample_count is not None:
                    result_parts.append(f"Sample Count: {sample_count}")
                result_parts.append("")
                
                generated_audio = []  # Track successful audio for rendering
                
                for i, prediction in enumerate(predictions):
                    result_parts.append(f"Audio {i + 1}:")
                    
                    # Extract audio data - Lyria uses 'bytesBase64Encoded' like Imagen
                    if 'bytesBase64Encoded' in prediction:
                        audio_data = prediction['bytesBase64Encoded']
                        # Default to audio/mp3 if mimeType is not provided
                        mime_type = prediction.get('mimeType', 'audio/mp3')
                        
                        result_parts.append(f"- Format: {mime_type}")
                        result_parts.append(f"- Size: {len(audio_data)} characters (base64)")
                        
                        # Upload to asset proxy if enabled
                        if self.valves.AUTO_UPLOAD_MEDIA:
                            upload_result = await self._upload_to_asset_proxy(emitter, audio_data, mime_type)
                            
                            if upload_result['success']:
                                result_parts.append(f"- Upload: SUCCESS (Status: {upload_result['status_code']})")
                                result_parts.append(f"- Upload ID: {upload_result['upload_id']}")
                                result_parts.append(f"- Access URL: {upload_result['access_url']}")
                                result_parts.append(f"- Direct Link: {upload_result['access_url']}")
                                
                                # Add to successful audio for rendering
                                generated_audio.append({
                                    'url': upload_result['access_url'],
                                    'caption': f"Generated Music {i + 1} ({selected_model}): {prompt[:50]}..."
                                })
                            else:
                                result_parts.append("- Upload: FAILED")
                                result_parts.append(f"- Upload Error: {upload_result['error']}")
                                result_parts.append(f"- Status Code: {upload_result['status_code']}")
                                result_parts.append(f"- Response: {upload_result['response_text']}")
                                if upload_result['request_details']:
                                    req_details = upload_result['request_details']
                                    result_parts.append(f"- Request URL: {req_details['url']}")
                                    result_parts.append(f"- Data Length: {req_details['data_length']}")
                                    result_parts.append(f"- MIME Type: {req_details['mime_type']}")
                                result_parts.append(f"- Base64 data (first 100 chars): {audio_data[:100]}...")
                        else:
                            result_parts.append(f"- Base64 data (first 100 chars): {audio_data[:100]}...")
                    
                    # Extract safety information
                    if 'raiFilteredReason' in prediction:
                        result_parts.append(f"- Safety filter: {prediction['raiFilteredReason']}")
                    
                    result_parts.append("")
                
                # Add model metadata if available
                if 'modelDisplayName' in response_data:
                    result_parts.append(f"Model Display Name: {response_data['modelDisplayName']}")
                
                # Render audio to the user if any were successfully uploaded
                if generated_audio and __event_emitter__:
                    await emitter.progress_update("Rendering audio...")
                    for audio in generated_audio:
                        await emitter.emit_audio(audio['url'], audio['caption'])
                
                result = "\n".join(result_parts)
                
                await emitter.success_update(f"Generated and rendered {len(predictions)} music track(s) successfully!")
                return result
                
            else:
                error_data = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_data = error_json['error'].get('message', error_data)
                except:
                    pass
                
                raise ValueError(f"Music generation failed ({response.status_code}): {error_data}")
            
        except Exception as e:
            error_message = f"Music generation failed: {str(e)}"
            
            if "quota" in str(e).lower():
                error_message += "\n\nTroubleshooting:\n- Check your Vertex AI quota limits\n- Ensure billing is enabled for your project"
            elif "403" in str(e) or "permission" in str(e).lower():
                error_message += "\n\nTroubleshooting:\n- Verify service account has Vertex AI permissions\n- Check if Lyria API is enabled in your project"
            elif "400" in str(e):
                error_message += "\n\nTroubleshooting:\n- Check if the prompt meets content policy guidelines\n- Verify all parameters are valid\n- Ensure seed and sample_count are not both specified"
            elif "Invalid music model" in str(e):
                error_message += f"\n\nUse 'list_available_models()' to see all available models."
            elif "No service account JSON provided" in str(e):
                error_message += "\n\nTroubleshooting:\n- Configure your service account JSON in the tool settings\n- Ensure the JSON contains all required fields\n- Check that the service account has proper permissions"
            
            await emitter.error_update(error_message)
            return error_message


class VertexAITest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_image_no_auth(self):
        """Test image generation without authentication."""
        tools = Tools()
        response = await tools.generate_image("test prompt")
        self.assertIn("failed", response.lower())

    async def test_generate_music_no_auth(self):
        """Test music generation without authentication."""
        tools = Tools()
        response = await tools.generate_music("test prompt")
        self.assertIn("failed", response.lower())

    async def test_list_available_models(self):
        """Test listing available models."""
        tools = Tools()
        response = await tools.list_available_models()
        self.assertIn("imagen-4.0-generate-preview-05-20", response)
        self.assertIn("lyria-002", response)


if __name__ == "__main__":
    print("Running Vertex AI Media Generator tests...")
    unittest.main()
