#!/usr/bin/env python3
"""
Activate/Deactivate Workflow Script
Manages workflow activation state in n8n
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime


class WorkflowActivator:
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

    def activate_workflow(self, workflow_id):
        """Activate a workflow"""
        return self._set_workflow_active_state(workflow_id, True)

    def deactivate_workflow(self, workflow_id):
        """Deactivate a workflow"""
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
                print(f"ℹ️  Workflow '{workflow_name}' is already {state_str}")
                return {
                    'id': workflow_id,
                    'name': workflow_name,
                    'active': current_state,
                    'changed': False
                }

            # Use the dedicated activate/deactivate endpoints
            if active:
                action_url = f"{base_url}/api/v1/workflows/{workflow_id}/activate"
                action = "Activating"
            else:
                action_url = f"{base_url}/api/v1/workflows/{workflow_id}/deactivate"
                action = "Deactivating"

            print(f"🔄 {action} workflow '{workflow_name}'...")

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

                return {
                    'id': workflow_id,
                    'name': workflow_name,
                    'active': new_state,
                    'changed': True
                }
            else:
                raise Exception(f"Failed to change activation state. Current state: {new_state}")

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

    def list_all_workflows(self):
        """List all workflows with their activation status"""
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/workflows"
        headers = {}

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()

            workflows = response.json().get('data', [])
            return workflows
        except Exception as e:
            raise Exception(f"Failed to list workflows: {str(e)}")

    def activate_from_workspace(self, workspace_path):
        """Activate workflow using workspace metadata"""
        workspace = Path(workspace_path)
        metadata_file = workspace / "metadata.json"

        if not metadata_file.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_file}")

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        workflow_id = metadata.get('workflow_id')
        if not workflow_id:
            raise ValueError("No workflow_id found in metadata")

        workflow_name = metadata.get('workflow_name', 'Unknown')
        print(f"📁 Activating workflow from workspace: {workflow_name}")

        return self.activate_workflow(workflow_id)

    def batch_activate(self, workflow_ids, activate=True):
        """Activate or deactivate multiple workflows"""
        results = []
        action = "activation" if activate else "deactivation"
        print(f"\n🔄 Starting batch {action} for {len(workflow_ids)} workflows...")

        for workflow_id in workflow_ids:
            try:
                if activate:
                    result = self.activate_workflow(workflow_id)
                else:
                    result = self.deactivate_workflow(workflow_id)
                results.append(result)
            except Exception as e:
                print(f"❌ Failed for workflow {workflow_id}: {e}")
                results.append({
                    'id': workflow_id,
                    'error': str(e)
                })

        # Summary
        successful = [r for r in results if r.get('changed')]
        already_done = [r for r in results if 'changed' in r and not r['changed']]
        failed = [r for r in results if 'error' in r]

        print(f"\n📊 Batch {action} summary:")
        print(f"   ✅ Successfully changed: {len(successful)}")
        print(f"   ℹ️  Already in target state: {len(already_done)}")
        print(f"   ❌ Failed: {len(failed)}")

        return results


def main():
    parser = argparse.ArgumentParser(description='Activate/Deactivate n8n workflows')

    # Commands
    parser.add_argument('command', choices=['activate', 'deactivate', 'status', 'list'],
                        help='Command to execute')

    # Options
    parser.add_argument('--workflow-id', help='Workflow ID')
    parser.add_argument('--workspace', help='Path to workspace directory')
    parser.add_argument('--config', help='Path to config.json')
    parser.add_argument('--all', action='store_true',
                        help='Apply to all workflows (use with caution)')
    parser.add_argument('--batch', nargs='+', metavar='ID',
                        help='List of workflow IDs for batch operations')

    args = parser.parse_args()

    try:
        activator = WorkflowActivator(args.config)

        if args.command == 'list':
            # List all workflows
            workflows = activator.list_all_workflows()
            print(f"\n📋 Found {len(workflows)} workflows:")
            print("-" * 60)

            active_count = 0
            for workflow in workflows:
                status = "🟢 Active" if workflow.get('active') else "⚪ Inactive"
                active_count += 1 if workflow.get('active') else 0
                print(f"{status}  {workflow.get('name', 'Unknown'):30} (ID: {workflow.get('id')})")

            print("-" * 60)
            print(f"Summary: {active_count} active, {len(workflows) - active_count} inactive")

        elif args.command == 'status':
            # Get status of specific workflow
            if args.workflow_id:
                workflow_id = args.workflow_id
            elif args.workspace:
                # Get workflow ID from workspace
                workspace = Path(args.workspace)
                metadata_file = workspace / "metadata.json"
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                workflow_id = metadata.get('workflow_id')
            else:
                parser.error("Either --workflow-id or --workspace is required for status command")

            status = activator.get_workflow_status(workflow_id)
            print(f"\n📊 Workflow Status:")
            print(f"   Name: {status['name']}")
            print(f"   ID: {status['id']}")
            print(f"   Active: {'🟢 Yes' if status['active'] else '⚪ No'}")
            print(f"   Nodes: {status['node_count']}")
            if status.get('created_at'):
                print(f"   Created: {status['created_at']}")
            if status.get('updated_at'):
                print(f"   Updated: {status['updated_at']}")

        elif args.command in ['activate', 'deactivate']:
            activate = (args.command == 'activate')

            if args.batch:
                # Batch operation
                results = activator.batch_activate(args.batch, activate)

            elif args.all:
                # Apply to all workflows
                confirm = input(f"⚠️  Are you sure you want to {args.command} ALL workflows? (yes/no): ")
                if confirm.lower() != 'yes':
                    print("Operation cancelled")
                    return 1

                workflows = activator.list_all_workflows()
                workflow_ids = [w['id'] for w in workflows]
                results = activator.batch_activate(workflow_ids, activate)

            elif args.workspace:
                # Use workspace
                if activate:
                    result = activator.activate_from_workspace(args.workspace)
                else:
                    workspace = Path(args.workspace)
                    metadata_file = workspace / "metadata.json"
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    workflow_id = metadata.get('workflow_id')
                    result = activator.deactivate_workflow(workflow_id)

            elif args.workflow_id:
                # Single workflow by ID
                if activate:
                    result = activator.activate_workflow(args.workflow_id)
                else:
                    result = activator.deactivate_workflow(args.workflow_id)

            else:
                parser.error(f"Either --workflow-id, --workspace, --batch, or --all is required for {args.command} command")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())