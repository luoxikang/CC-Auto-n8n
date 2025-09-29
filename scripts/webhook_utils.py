#!/usr/bin/env python3
"""
Webhook Utilities for n8n Integration
Provides functions for webhook URL extraction, testing, and triggering
"""

import json
import requests
import argparse
from pathlib import Path
from datetime import datetime
import time
import sys


class WebhookManager:
    def __init__(self, config_path=None):
        """Initialize webhook manager with configuration"""
        if not config_path:
            parent_config = Path(__file__).parent.parent / "config.json"
            if parent_config.exists():
                config_path = parent_config

        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "n8n_api": {
                    "base_url": "https://n8n.x-silicon.club"
                }
            }

        self.base_url = self.config['n8n_api']['base_url']

    def extract_webhook_urls(self, workflow_json):
        """Extract webhook URLs from workflow JSON"""
        webhooks = []

        if isinstance(workflow_json, str):
            workflow_json = json.loads(workflow_json)

        for node in workflow_json.get('nodes', []):
            if 'webhook' in node.get('type', '').lower():
                webhook_info = {
                    'node_name': node.get('name', 'Unnamed'),
                    'path': node['parameters'].get('path', ''),
                    'method': node['parameters'].get('method', 'GET'),
                    'webhook_id': node.get('webhookId', ''),
                    'response_mode': node['parameters'].get('responseMode', 'onReceived')
                }

                # Generate URLs
                if webhook_info['path']:
                    webhook_info['production_url'] = f"{self.base_url}/webhook/{webhook_info['path']}"
                    webhook_info['test_url'] = f"{self.base_url}/webhook-test/{webhook_info['path']}"
                elif webhook_info['webhook_id']:
                    webhook_info['production_url'] = f"{self.base_url}/webhook/{webhook_info['webhook_id']}"
                    webhook_info['test_url'] = f"{self.base_url}/webhook-test/{webhook_info['webhook_id']}"

                webhooks.append(webhook_info)

        return webhooks

    def trigger_webhook(self, webhook_url, data=None, headers=None, method='POST', timeout=30):
        """Trigger a webhook and return the response"""
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        if data is None:
            data = {
                'trigger': 'manual',
                'timestamp': datetime.now().isoformat(),
                'source': 'webhook_utils'
            }

        try:
            print(f"🚀 Triggering webhook: {webhook_url}")
            print(f"📦 Method: {method}")
            print(f"📊 Payload: {json.dumps(data, indent=2)}")

            start_time = time.time()

            if method.upper() == 'GET':
                response = requests.get(webhook_url, params=data, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(webhook_url, json=data, headers=headers, timeout=timeout)
            elif method.upper() == 'PUT':
                response = requests.put(webhook_url, json=data, headers=headers, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(webhook_url, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            duration = time.time() - start_time

            result = {
                'success': response.ok,
                'status_code': response.status_code,
                'duration': duration,
                'headers': dict(response.headers),
                'execution_id': response.headers.get('x-n8n-execution-id'),
                'response_data': None
            }

            # Parse response
            try:
                result['response_data'] = response.json()
            except:
                result['response_data'] = response.text

            # Print results
            print(f"\n✅ Response received in {duration:.2f} seconds")
            print(f"📍 Status: {response.status_code}")
            if result['execution_id']:
                print(f"🔖 Execution ID: {result['execution_id']}")

            return result

        except requests.exceptions.Timeout:
            print(f"❌ Timeout after {timeout} seconds")
            return {'success': False, 'error': 'Request timeout'}
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            print(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}

    def test_webhook(self, webhook_url, test_data=None):
        """Test a webhook with sample data"""
        if test_data is None:
            test_data = {
                'test': True,
                'timestamp': datetime.now().isoformat(),
                'sample_data': {
                    'name': 'Test User',
                    'email': 'test@example.com',
                    'action': 'test_webhook'
                }
            }

        print("🧪 Testing webhook...")
        return self.trigger_webhook(webhook_url, test_data)

    def verify_webhook_registration(self, webhook_url, method='POST'):
        """Verify if a webhook is registered and accessible"""
        try:
            print(f"🔍 Verifying webhook registration: {webhook_url}")

            # Try OPTIONS request first
            options_response = requests.options(webhook_url, timeout=5)
            print(f"   OPTIONS response: {options_response.status_code}")

            # Try HEAD request
            head_response = requests.head(webhook_url, timeout=5)
            print(f"   HEAD response: {head_response.status_code}")

            # Check if webhook endpoint exists (not 404)
            if options_response.status_code == 404 and head_response.status_code == 404:
                print("❌ Webhook endpoint not found")
                return {'registered': False, 'reason': 'endpoint_not_found'}

            # Check allowed methods
            allow_header = options_response.headers.get('Allow', '')
            if allow_header and method not in allow_header:
                print(f"❌ Method {method} not allowed. Allowed methods: {allow_header}")
                return {'registered': False, 'reason': 'method_not_allowed', 'allowed': allow_header}

            print("✅ Webhook appears to be registered")
            return {'registered': True}

        except requests.exceptions.ConnectionError:
            return {'registered': False, 'reason': 'connection_error'}
        except Exception as e:
            return {'registered': False, 'reason': str(e)}

    def trigger_test_webhook(self, webhook_url, data=None, listen_duration=120):
        """Trigger webhook in test mode (for n8n test webhooks)"""
        # Convert production URL to test URL if needed
        if '/webhook/' in webhook_url and '/webhook-test/' not in webhook_url:
            test_url = webhook_url.replace('/webhook/', '/webhook-test/')
            print(f"📝 Using test webhook URL: {test_url}")
        else:
            test_url = webhook_url

        if data is None:
            data = {
                'mode': 'test',
                'timestamp': datetime.now().isoformat(),
                'listen_duration': listen_duration
            }

        print(f"🧪 Triggering test webhook (listening for {listen_duration}s)...")
        print("⚠️  Note: In n8n UI, click 'Listen for Test Event' before sending this request")

        return self.trigger_webhook(test_url, data, method='POST')

    def save_webhook_info(self, workspace_path, webhook_info):
        """Save webhook information to workspace metadata"""
        workspace = Path(workspace_path)
        metadata_file = workspace / "metadata.json"

        # Load existing metadata
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}

        # Update webhook configuration
        metadata['webhook_config'] = webhook_info
        metadata['last_updated'] = datetime.now().isoformat()

        # Save updated metadata
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"💾 Webhook info saved to {metadata_file}")

    def load_webhook_info(self, workspace_path):
        """Load webhook information from workspace metadata"""
        workspace = Path(workspace_path)
        metadata_file = workspace / "metadata.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                return metadata.get('webhook_config', {})

        return {}

    def batch_trigger(self, webhook_urls, data=None, delay=1):
        """Trigger multiple webhooks with optional delay"""
        results = []

        for i, url in enumerate(webhook_urls, 1):
            print(f"\n[{i}/{len(webhook_urls)}] Processing webhook...")
            result = self.trigger_webhook(url, data)
            results.append({
                'url': url,
                'result': result
            })

            if i < len(webhook_urls):
                print(f"⏳ Waiting {delay} seconds...")
                time.sleep(delay)

        return results


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Webhook utilities for n8n workflows')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract webhook URLs from workflow')
    extract_parser.add_argument('--workflow', required=True, help='Path to workflow JSON file')
    extract_parser.add_argument('--save', help='Save to workspace metadata')

    # Trigger command
    trigger_parser = subparsers.add_parser('trigger', help='Trigger a webhook')
    trigger_parser.add_argument('--url', required=True, help='Webhook URL')
    trigger_parser.add_argument('--data', help='JSON data to send')
    trigger_parser.add_argument('--method', default='POST', help='HTTP method')
    trigger_parser.add_argument('--timeout', type=int, default=30, help='Request timeout')

    # Test command
    test_parser = subparsers.add_parser('test', help='Test a webhook')
    test_parser.add_argument('--url', required=True, help='Webhook URL to test')
    test_parser.add_argument('--workspace', help='Workspace path to load webhook info from')

    # Batch command
    batch_parser = subparsers.add_parser('batch', help='Trigger multiple webhooks')
    batch_parser.add_argument('--urls', nargs='+', required=True, help='List of webhook URLs')
    batch_parser.add_argument('--data', help='JSON data to send')
    batch_parser.add_argument('--delay', type=int, default=1, help='Delay between triggers')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    manager = WebhookManager()

    if args.command == 'extract':
        # Load workflow JSON
        with open(args.workflow, 'r') as f:
            workflow_json = json.load(f)

        # Extract webhook URLs
        webhooks = manager.extract_webhook_urls(workflow_json)

        if webhooks:
            print("🔍 Found webhooks:")
            for webhook in webhooks:
                print(f"\n📌 Node: {webhook['node_name']}")
                print(f"   Method: {webhook['method']}")
                print(f"   Production URL: {webhook.get('production_url', 'N/A')}")
                print(f"   Test URL: {webhook.get('test_url', 'N/A')}")

            # Save if requested
            if args.save:
                webhook_info = {
                    'webhooks': webhooks,
                    'extracted_at': datetime.now().isoformat(),
                    'workflow_file': args.workflow
                }
                manager.save_webhook_info(args.save, webhook_info)
        else:
            print("❌ No webhooks found in workflow")

    elif args.command == 'trigger':
        data = None
        if args.data:
            try:
                data = json.loads(args.data)
            except:
                print("⚠️  Invalid JSON data, sending as string")
                data = {'data': args.data}

        result = manager.trigger_webhook(args.url, data, method=args.method, timeout=args.timeout)

        if result['success']:
            print("\n📄 Response:")
            print(json.dumps(result['response_data'], indent=2))
        else:
            print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")

    elif args.command == 'test':
        # Load webhook info if workspace provided
        webhook_url = args.url

        if args.workspace:
            webhook_info = manager.load_webhook_info(args.workspace)
            if webhook_info and 'webhooks' in webhook_info:
                print(f"📁 Loaded webhook info from {args.workspace}")

        result = manager.test_webhook(webhook_url)

        if result['success']:
            print("\n✅ Test successful!")
            print(f"📄 Response: {json.dumps(result['response_data'], indent=2)}")
        else:
            print(f"\n❌ Test failed: {result.get('error', 'Unknown error')}")

    elif args.command == 'batch':
        data = None
        if args.data:
            try:
                data = json.loads(args.data)
            except:
                data = {'data': args.data}

        results = manager.batch_trigger(args.urls, data, args.delay)

        # Summary
        print("\n📊 Batch Results:")
        success_count = sum(1 for r in results if r['result']['success'])
        print(f"✅ Success: {success_count}/{len(results)}")

        for i, result in enumerate(results, 1):
            status = "✅" if result['result']['success'] else "❌"
            print(f"{status} [{i}] {result['url'][:50]}...")


if __name__ == "__main__":
    main()