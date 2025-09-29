#!/usr/bin/env python3
"""
Import Workflow Script
Imports workflow JSON to n8n via API
"""

import os
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime


class WorkflowImporter:
    def __init__(self, config_path=None):
        """Initialize with configuration"""
        # Try to find config.json in parent directory if not specified
        if not config_path:
            parent_config = Path(__file__).parent.parent / "config.json"
            if parent_config.exists():
                config_path = parent_config

        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            # Default configuration
            self.config = {
                "n8n_api": {
                    "base_url": os.getenv("N8N_API_URL", "http://localhost:5678"),
                    "api_key": os.getenv("N8N_API_KEY", "")
                }
            }

    def extract_webhook_urls(self, workflow_json):
        """Extract webhook URLs from workflow JSON"""
        webhooks = []

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
                    webhook_info['production_url'] = f"{self.config['n8n_api']['base_url']}/webhook/{webhook_info['path']}"
                    webhook_info['test_url'] = f"{self.config['n8n_api']['base_url']}/webhook-test/{webhook_info['path']}"
                elif webhook_info['webhook_id']:
                    webhook_info['production_url'] = f"{self.config['n8n_api']['base_url']}/webhook/{webhook_info['webhook_id']}"
                    webhook_info['test_url'] = f"{self.config['n8n_api']['base_url']}/webhook-test/{webhook_info['webhook_id']}"

                webhooks.append(webhook_info)

        return webhooks

    def import_workflow(self, workspace_path, extract_webhook=False, activate=True):
        """Import workflow from workspace to n8n"""
        workspace = Path(workspace_path)
        workflow_file = workspace / "workflow.json"

        if not workflow_file.exists():
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        # Load workflow JSON
        with open(workflow_file, 'r') as f:
            workflow_data = json.load(f)

        # Clean workflow data for API
        # Remove fields that are read-only or not allowed during creation
        # Note: 'active' field must be removed as it's read-only during creation
        fields_to_remove = ['id', 'active', 'createdAt', 'updatedAt']
        for field in fields_to_remove:
            workflow_data.pop(field, None)

        # Prepare API request
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/workflows"
        headers = {
            "Content-Type": "application/json"
        }

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        # Check if workflow has an ID (update) or not (create)
        workflow_id = workflow_data.get('id')

        try:
            if workflow_id:
                # Update existing workflow
                response = requests.put(
                    f"{api_url}/{workflow_id}",
                    json=workflow_data,
                    headers=headers
                )
            else:
                # Create new workflow
                response = requests.post(
                    api_url,
                    json=workflow_data,
                    headers=headers
                )

            response.raise_for_status()

            # Parse response
            result = response.json()
            workflow_id = result.get('id', workflow_id)

            # Extract webhook URLs if requested
            if extract_webhook:
                webhooks = self.extract_webhook_urls(workflow_data)
                if webhooks:
                    print(f"\n🔗 Found {len(webhooks)} webhook(s):")
                    for webhook in webhooks:
                        print(f"   📌 {webhook['node_name']}: {webhook.get('production_url', 'N/A')}")

                    # Save webhook info to metadata
                    self.save_webhook_info(workspace, webhooks)

            # Activate workflow if requested (for webhook registration)
            if activate:
                print(f"📝 Activating workflow to ensure webhook registration...")
                if self.activate_workflow(workflow_id):
                    print(f"✅ Workflow activated successfully")
                else:
                    print(f"⚠️  Could not activate workflow, webhook may not work")

            # Update metadata
            self.update_import_metadata(workspace, workflow_id, result)

            # Verify webhook registration if webhooks exist
            if extract_webhook and webhooks:
                print("\n🔍 Verifying webhook registration...")
                from webhook_utils import WebhookManager
                webhook_mgr = WebhookManager()

                for webhook in webhooks:
                    prod_url = webhook.get('production_url')
                    if prod_url:
                        verification = webhook_mgr.verify_webhook_registration(prod_url)
                        if not verification.get('registered'):
                            print(f"⚠️  Webhook may not be properly registered: {verification.get('reason')}")
                            print("    Try using test mode or re-activating the workflow")

            # Log import
            self.log_import(workspace, workflow_id, "success")

            print(f"✅ Workflow imported successfully")
            print(f"   workflow_id: {workflow_id}")

            return workflow_id

        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}: {json.dumps(error_detail, indent=2)}"
                except:
                    error_msg = f"{error_msg}: {e.response.text}"

            # Log error
            self.log_import(workspace, None, "failed", error_msg)

            raise Exception(f"Import failed: {error_msg}")

    def save_webhook_info(self, workspace, webhooks):
        """Save webhook information to workspace metadata"""
        metadata_file = workspace / "metadata.json"

        # Load existing metadata
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}

        # Update webhook configuration
        metadata['webhook_config'] = {
            'webhooks': webhooks,
            'extracted_at': datetime.now().isoformat()
        }

        # Save updated metadata
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def update_import_metadata(self, workspace, workflow_id, api_response):
        """Update metadata with import information"""
        metadata_path = workspace / "metadata.json"

        metadata = {}
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

        # Update with import info
        metadata["workflow_id"] = workflow_id
        metadata["last_import"] = {
            "timestamp": datetime.now().isoformat(),
            "workflow_id": workflow_id,
            "node_count": len(api_response.get('nodes', []))
        }

        # Save metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def log_import(self, workspace, workflow_id, status, error=None):
        """Log import operation"""
        log_dir = workspace / "logs"
        log_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"import_{timestamp}.log"

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": "import",
            "status": status,
            "workflow_id": workflow_id,
            "api_url": self.config['n8n_api']['base_url']
        }

        if error:
            log_entry["error"] = error

        with open(log_file, 'w') as f:
            json.dump(log_entry, f, indent=2)

    def validate_workflow(self, workflow_data):
        """Basic validation of workflow JSON structure"""
        required_fields = ['name', 'nodes', 'connections']

        for field in required_fields:
            if field not in workflow_data:
                raise ValueError(f"Missing required field: {field}")

        # Check nodes structure
        if not isinstance(workflow_data['nodes'], list):
            raise ValueError("'nodes' must be an array")

        # Check each node has required fields
        for i, node in enumerate(workflow_data['nodes']):
            if 'name' not in node:
                raise ValueError(f"Node {i} missing 'name' field")
            if 'type' not in node:
                raise ValueError(f"Node {i} missing 'type' field")
            if 'position' not in node:
                raise ValueError(f"Node {i} missing 'position' field")

        return True

    def activate_workflow(self, workflow_id):
        """Activate a workflow by setting active to true"""
        return self._set_workflow_active_state(workflow_id, True)

    def deactivate_workflow(self, workflow_id):
        """Deactivate a workflow by setting active to false"""
        return self._set_workflow_active_state(workflow_id, False)

    def _set_workflow_active_state(self, workflow_id, active):
        """Set workflow active state (true/false)"""
        base_url = self.config['n8n_api']['base_url']
        headers = {"Content-Type": "application/json"}

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            # First, GET the current workflow data to check state
            get_url = f"{base_url}/api/v1/workflows/{workflow_id}"
            print(f"📋 Fetching workflow {workflow_id}...")
            response = requests.get(get_url, headers=headers)
            response.raise_for_status()

            workflow_data = response.json()
            current_state = workflow_data.get('active', False)
            workflow_name = workflow_data.get('name', 'Unknown')

            # Check if already in desired state
            if current_state == active:
                state_str = "active" if active else "inactive"
                print(f"ℹ️  Workflow is already {state_str}")
                return workflow_id

            # Use the dedicated activate/deactivate endpoints
            if active:
                action_url = f"{base_url}/api/v1/workflows/{workflow_id}/activate"
                action = "Activating"
            else:
                action_url = f"{base_url}/api/v1/workflows/{workflow_id}/deactivate"
                action = "Deactivating"

            print(f"🔄 {action} workflow...")

            # POST to the activation/deactivation endpoint
            response = requests.post(action_url, headers=headers)
            response.raise_for_status()

            # Verify the state change
            response = requests.get(get_url, headers=headers)
            response.raise_for_status()
            result = response.json()
            new_state = result.get('active', False)

            if new_state == active:
                state_str = "activated" if active else "deactivated"
                print(f"✅ Workflow {state_str} successfully")
                print(f"   ID: {workflow_id}")
                print(f"   Name: {workflow_name}")
                print(f"   Active: {new_state}")
            else:
                raise Exception(f"Failed to change activation state. Current state: {new_state}")

            return workflow_id

        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}: {json.dumps(error_detail, indent=2)}"
                except:
                    error_msg = f"{error_msg}: {e.response.text}"

            action = "activate" if active else "deactivate"
            raise Exception(f"Failed to {action} workflow: {error_msg}")

    def get_workflow_status(self, workflow_id):
        """Get the current activation status of a workflow"""
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/workflows/{workflow_id}"
        headers = {}

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()

            workflow_data = response.json()
            return {
                'id': workflow_id,
                'name': workflow_data.get('name', 'Unknown'),
                'active': workflow_data.get('active', False),
                'node_count': len(workflow_data.get('nodes', [])),
                'created_at': workflow_data.get('createdAt'),
                'updated_at': workflow_data.get('updatedAt')
            }
        except Exception as e:
            raise Exception(f"Failed to get workflow status: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description='Import workflow to n8n')
    parser.add_argument('--workspace', required=True, help='Path to workspace directory')
    parser.add_argument('--config', help='Path to config.json')
    parser.add_argument('--validate-only', action='store_true', help='Only validate, don\'t import')
    parser.add_argument('--extract-webhook', action='store_true', help='Extract and save webhook URLs after import')
    parser.add_argument('--activate', action='store_true', help='Activate workflow after import')

    args = parser.parse_args()

    try:
        importer = WorkflowImporter(args.config)

        if args.validate_only:
            # Just validate the workflow
            workspace = Path(args.workspace)
            workflow_file = workspace / "workflow.json"

            with open(workflow_file, 'r') as f:
                workflow_data = json.load(f)

            importer.validate_workflow(workflow_data)
            print("✅ Workflow validation passed")

            # Also check for webhooks if requested
            if args.extract_webhook:
                webhooks = importer.extract_webhook_urls(workflow_data)
                if webhooks:
                    print(f"\n🔗 Found {len(webhooks)} webhook(s):")
                    for webhook in webhooks:
                        print(f"   📌 {webhook['node_name']}: {webhook.get('test_url', 'N/A')}")
                else:
                    print("\nℹ️  No webhooks found in workflow")
        else:
            # Import workflow (with activation handled inside import_workflow if requested)
            workflow_id = importer.import_workflow(
                args.workspace,
                extract_webhook=args.extract_webhook,
                activate=args.activate
            )

            return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())