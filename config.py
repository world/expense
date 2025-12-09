"""
Configuration management for the expense helper.
Handles loading config.json and LLM bootstrapping.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from anthropic import Anthropic


class Config:
    """Manages application configuration."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config_data: Dict[str, Any] = {}
        self.llm_client: Optional[Any] = None  # Can be OpenAI or Anthropic client
        self.llm_provider: Optional[str] = None  # Track which provider
        
    def load(self) -> Tuple[bool, Optional[str]]:
        """
        Load configuration file.
        
        Returns:
            Tuple of (success, error_message)
        """
        # Load main config
        if not self.config_path.exists():
            return False, f"Config file not found: {self.config_path}"
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON in {self.config_path}: {e}"
        except Exception as e:
            return False, f"Error reading {self.config_path}: {e}"
        
        # Validate page_selectors section exists
        if 'page_selectors' not in self.config_data:
            return False, "Config file missing 'page_selectors' section"
        
        return True, None
    
    def get_llm_config(self) -> Dict[str, str]:
        """Get LLM configuration from config."""
        return self.config_data.get('llm', {})
    
    def is_llm_configured(self) -> bool:
        """Check if LLM is properly configured."""
        llm = self.get_llm_config()
        return bool(
            llm.get('api_key') and
            llm.get('model') and
            llm.get('base_url')
        )
    
    def fetch_available_models(self, api_key: str, base_url: str, provider: str) -> List[str]:
        """
        Dynamically fetch available models from the LLM API.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
            provider: Provider type ("openai", "anthropic", or "other")
            
        Returns:
            List of available model IDs
        """
        import requests
        
        try:
            if provider == "anthropic":
                # Anthropic has a models list endpoint
                print("   Fetching Claude models from Anthropic API...")
                
                response = requests.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    models_data = response.json().get('data', [])
                    model_ids = [m['id'] for m in models_data]
                    # Sort with newest first
                    model_ids.sort(reverse=True)
                    print(f"   ✅ Found {len(model_ids)} models")
                    return model_ids
                else:
                    print(f"   ⚠️  API returned {response.status_code}: {response.text[:100]}")
                    return []
                    
            elif provider == "openai":
                # Use OpenAI's models endpoint
                print("   Fetching models from OpenAI API...")
                
                temp_client = OpenAI(api_key=api_key, base_url=base_url)
                models = temp_client.models.list()
                model_ids = [model.id for model in models.data]
                
                # Filter to GPT/O1/O3 models (not embeddings, whisper, dall-e, etc)
                gpt_models = [m for m in model_ids if any(x in m.lower() for x in ['gpt', 'o1', 'o3', 'chatgpt'])]
                gpt_models.sort(reverse=True)
                
                print(f"   ✅ Found {len(gpt_models)} GPT models")
                return gpt_models if gpt_models else model_ids[:20]
                
            else:
                # Try OpenAI-compatible API for custom providers
                print("   Fetching models from custom API...")
                temp_client = OpenAI(api_key=api_key, base_url=base_url)
                models = temp_client.models.list()
                model_ids = [model.id for model in models.data]
                model_ids.sort()
                print(f"   ✅ Found {len(model_ids)} models")
                return model_ids
                
        except Exception as e:
            print(f"⚠️  Could not fetch models: {e}")
            return []
    
    def prompt_for_llm_config(self) -> Optional[Dict[str, str]]:
        """
        Prompt user for missing LLM configuration values.
        
        Returns:
            Dict with api_key, model, and base_url
        """
        print("\n🔐 LLM Configuration Required")
        print("=" * 60)
        
        llm = self.get_llm_config()
        
        # Provider selection first
        print("\nSelect your LLM provider:")
        print("  1. OpenAI (ChatGPT, GPT-4, etc.)")
        print("  2. Anthropic (Claude)")
        print("  3. Other (custom OpenAI-compatible API)")
        
        provider_choice = input("\nChoose provider [1]: ").strip() or "1"
        
        # Set base URL and provider type based on choice
        if provider_choice == "1":
            base_url = "https://api.openai.com/v1"
            provider_name = "OpenAI"
            provider_type = "openai"
        elif provider_choice == "2":
            base_url = "https://api.anthropic.com/v1"
            provider_name = "Anthropic"
            provider_type = "anthropic"
        elif provider_choice == "3":
            base_url = input("Enter custom API base URL: ").strip()
            provider_name = "Custom"
            provider_type = "other"
        else:
            # Default to OpenAI
            base_url = "https://api.openai.com/v1"
            provider_name = "OpenAI"
            provider_type = "openai"
        
        print(f"✅ Selected: {provider_name}")
        print(f"   Base URL: {base_url}")
        
        # API Key with validation loop
        api_key = llm.get('api_key', '')
        key_valid = False
        max_attempts = 3
        attempt = 0
        
        while not key_valid and attempt < max_attempts:
            attempt += 1
            
            if not api_key or attempt > 1:
                api_key = input(f"\nEnter {provider_name} API Key: ").strip()
            else:
                print(f"\nUsing existing API key: {api_key[:10]}...")
                response = input("Use this key? [Y/n]: ").strip().lower()
                if response == 'n':
                    api_key = input(f"Enter {provider_name} API Key: ").strip()
            
            # Validate the API key
            print("🔐 Validating API key...")
            try:
                # Create appropriate client and validate
                if provider_type == "anthropic":
                    # Use Anthropic client for validation
                    temp_client = Anthropic(api_key=api_key)
                    # Make a simple call to validate
                    temp_client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=10,
                        messages=[{"role": "user", "content": "test"}]
                    )
                else:
                    # Use OpenAI client for OpenAI and other providers
                    temp_client = OpenAI(api_key=api_key, base_url=base_url)
                    # Try to list models as validation
                    temp_client.models.list()
                
                print("✅ API key is valid!")
                key_valid = True
            except Exception as e:
                error_msg = str(e).lower()
                if "authentication" in error_msg or "unauthorized" in error_msg or "invalid" in error_msg or "401" in error_msg:
                    print(f"❌ Invalid API key: Authentication failed")
                    if attempt < max_attempts:
                        print(f"   Please try again ({attempt}/{max_attempts} attempts)")
                    api_key = ""  # Clear invalid key
                else:
                    print(f"⚠️  Could not validate key: {e}")
                    # Allow continuing with unvalidated key for non-auth errors
                    response = input("Continue anyway? [y/N]: ").strip().lower()
                    if response == 'y':
                        key_valid = True
                    else:
                        api_key = ""
        
        if not key_valid:
            print(f"\n❌ Failed to authenticate after {max_attempts} attempts.")
            print("Please check your API key and try again.")
            return None
        
        # Fetch available models
        print("\n🔍 Fetching available models...")
        available_models = self.fetch_available_models(api_key, base_url, provider_type)
        
        # Model selection
        model = llm.get('model', '')
        
        if available_models:
            print(f"\n📋 Available models ({len(available_models)}):")
            # Show first 10 models
            display_count = min(10, len(available_models))
            for i, m in enumerate(available_models[:display_count], 1):
                print(f"  {i}. {m}")
            
            if len(available_models) > display_count:
                print(f"  ... and {len(available_models) - display_count} more")
            
            default_model = available_models[0]
            print(f"\nDefault: {default_model}")
            
            choice = input(f"Choose model number or type name [1]: ").strip()
            
            if not choice or choice == '1':
                model = default_model
            elif choice.isdigit() and 1 <= int(choice) <= len(available_models):
                model = available_models[int(choice) - 1]
            else:
                # Assume they typed a model name
                model = choice
            
            print(f"✅ Selected: {model}")
        else:
            # Fallback if we couldn't fetch models
            if not model:
                model = input("\nEnter LLM Model [gpt-4]: ").strip() or "gpt-4"
            else:
                response = input(f"\nUse model '{model}'? [Y/n]: ").strip().lower()
                if response == 'n':
                    model = input("Enter LLM Model: ").strip()
        
        result = {
            'api_key': api_key,
            'model': model,
            'base_url': base_url,
            'provider': provider_type
        }
        
        # Update in-memory config
        self.config_data['llm'] = result
        self.llm_provider = provider_type
        
        # Auto-save
        self.save_config()
        print(f"✅ Saved to {self.config_path}")
        
        return result
    
    def save_config(self):
        """Save current config back to file."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config_data, f, indent=2)
    
    def test_llm_connection(self, logger=None) -> Tuple[bool, Optional[str]]:
        """
        Test LLM connectivity with a simple API call.
        
        Returns:
            Tuple of (success, error_message)
        """
        llm = self.get_llm_config()
        provider = llm.get('provider', 'openai')
        
        if logger:
            logger.info("Testing LLM connection...")
        else:
            print("Testing LLM connection...")
        
        try:
            if provider == "anthropic":
                # Create Anthropic client
                self.llm_client = Anthropic(api_key=llm['api_key'])
                self.llm_provider = "anthropic"
                
                # Simple test call
                response = self.llm_client.messages.create(
                    model=llm['model'],
                    max_tokens=50,
                    messages=[{"role": "user", "content": "Return this JSON: {\"test\": \"success\"}"}]
                )
                
                # Anthropic returns content differently
                if logger:
                    logger.info("✅ LLM connection successful!")
                else:
                    print("✅ LLM connection successful!")
                return True, None
            else:
                # Create OpenAI client (for OpenAI and other providers)
                self.llm_client = OpenAI(
                    api_key=llm['api_key'],
                    base_url=llm['base_url']
                )
                self.llm_provider = provider
                
                # Simple test call
                response = self.llm_client.chat.completions.create(
                    model=llm['model'],
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant. Respond only with valid JSON."},
                        {"role": "user", "content": "Return this JSON: {\"test\": \"success\"}"}
                    ],
                    temperature=0,
                    max_tokens=50
                )
                
                content = response.choices[0].message.content.strip()
                
                # Try to parse as JSON
                try:
                    result = json.loads(content)
                    if result.get('test') == 'success':
                        if logger:
                            logger.info("✅ LLM connection successful!")
                        else:
                            print("✅ LLM connection successful!")
                        return True, None
                except json.JSONDecodeError:
                    pass
                
                # If we got here, response was not as expected but API worked
                if logger:
                    logger.info("✅ LLM API responded (test result not as expected, but connection works)")
                else:
                    print("✅ LLM API responded (test result not as expected, but connection works)")
                return True, None
            
        except Exception as e:
            error_msg = f"LLM connection failed: {str(e)}"
            if logger:
                logger.error(error_msg)
            else:
                print(f"❌ {error_msg}")
            return False, error_msg
    
    def bootstrap_llm(self, logger=None) -> bool:
        """
        Ensure LLM is configured and working.
        Prompts user if needed and tests connection.
        
        Returns:
            True if LLM is ready, False otherwise
        """
        # Check if configured
        if not self.is_llm_configured():
            if logger:
                logger.warning("LLM not configured in config.json")
            result = self.prompt_for_llm_config()
            
            # If prompt_for_llm_config returns None, authentication failed
            if result is None:
                if logger:
                    logger.error("Failed to configure LLM. Cannot proceed.")
                return False
        
        # Test connection with a simple call
        success, error = self.test_llm_connection(logger)
        
        if success:
            return True
        
        # If test fails after successful key validation, offer to reconfigure
        if logger:
            logger.error(f"LLM connection test failed: {error}")
        else:
            print(f"\n❌ LLM connection test failed: {error}")
        
        retry = input("Would you like to re-enter LLM configuration? [Y/n]: ").strip().lower()
        if retry != 'n':
            result = self.prompt_for_llm_config()
            if result is None:
                return False
            # Test again
            success, error = self.test_llm_connection(logger)
            return success
        
        return False
    
    def get_expense_types(self) -> List[str]:
        """Get expense type names (for LLM prompts)."""
        expense_types = self.config_data.get('expense_types', {})
        if isinstance(expense_types, dict):
            return list(expense_types.keys())
        return expense_types  # Backward compatibility if it's still an array
    
    def get_expense_type_fields(self, expense_type: str) -> List[str]:
        """Get required fields for a specific expense type."""
        expense_types = self.config_data.get('expense_types', {})
        if isinstance(expense_types, dict):
            return expense_types.get(expense_type, [])
        return []  # No fields if using old array format
    
    def get_oracle_url(self) -> str:
        """Get Oracle expenses URL."""
        return self.config_data.get('oracle_url', '')
    
    def get_selector(self, *keys) -> Any:
        """
        Get a selector from config.json page_selectors section.
        
        Args:
            *keys: Path to the selector (e.g., 'buttons', 'create_item')
        """
        data = self.config_data.get('page_selectors', {})
        for key in keys:
            data = data.get(key, {})
            if not data:
                return None
        return data

