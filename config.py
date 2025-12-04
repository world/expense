"""
Configuration management for the expense helper.
Handles loading config.json and LLM bootstrapping.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


class Config:
    """Manages application configuration."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config_data: Dict[str, Any] = {}
        self.llm_client: Optional[OpenAI] = None
        
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
    
    def fetch_available_models(self, api_key: str, base_url: str) -> List[str]:
        """
        Fetch available models from the LLM API.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
            
        Returns:
            List of available model IDs
        """
        try:
            # Create temporary client
            temp_client = OpenAI(api_key=api_key, base_url=base_url)
            
            # Fetch models
            models = temp_client.models.list()
            
            # Extract model IDs and sort
            model_ids = [model.id for model in models.data]
            model_ids.sort()
            
            return model_ids
        except Exception as e:
            print(f"⚠️  Could not fetch models: {e}")
            return []
    
    def prompt_for_llm_config(self) -> Dict[str, str]:
        """
        Prompt user for missing LLM configuration values.
        
        Returns:
            Dict with api_key, model, and base_url
        """
        print("\n🔐 LLM Configuration Required")
        print("=" * 60)
        
        llm = self.get_llm_config()
        
        # Base URL first (needed to query models)
        base_url = llm.get('base_url', 'https://api.openai.com/v1')
        if not base_url:
            base_url = input("Enter API Base URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
        else:
            print(f"Using base URL: {base_url}")
            response = input(f"Change base URL? [y/N]: ").strip().lower()
            if response == 'y':
                base_url = input("Enter API Base URL: ").strip()
        
        # API Key
        api_key = llm.get('api_key', '')
        if not api_key:
            api_key = input("\nEnter LLM API Key: ").strip()
        else:
            print(f"\nUsing existing API key: {api_key[:10]}...")
        
        # Fetch available models
        print("\n🔍 Fetching available models...")
        available_models = self.fetch_available_models(api_key, base_url)
        
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
            'base_url': base_url
        }
        
        # Update in-memory config
        self.config_data['llm'] = result
        
        # Offer to save
        save = input("\n💾 Save these LLM settings to config.json? [Y/n]: ").strip().lower()
        if save != 'n':
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
        
        if logger:
            logger.info("Testing LLM connection...")
        else:
            print("Testing LLM connection...")
        
        try:
            # Create OpenAI client
            self.llm_client = OpenAI(
                api_key=llm['api_key'],
                base_url=llm['base_url']
            )
            
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
            self.prompt_for_llm_config()
        
        # Test connection (with retry)
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            success, error = self.test_llm_connection(logger)
            
            if success:
                return True
            
            if attempt < max_attempts:
                if logger:
                    logger.warning(f"Attempt {attempt}/{max_attempts} failed. Please check your LLM settings.")
                else:
                    print(f"\nAttempt {attempt}/{max_attempts} failed. Please check your LLM settings.")
                
                retry = input("Would you like to re-enter LLM configuration? [Y/n]: ").strip().lower()
                if retry != 'n':
                    self.prompt_for_llm_config()
                else:
                    return False
            else:
                if logger:
                    logger.error("Max attempts reached. Cannot proceed without working LLM connection.")
                else:
                    print("\n❌ Max attempts reached. Cannot proceed without working LLM connection.")
                return False
        
        return False
    
    def get_expense_types(self) -> List[Dict[str, Any]]:
        """Get expense type definitions."""
        return self.config_data.get('expense_types', [])
    
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

