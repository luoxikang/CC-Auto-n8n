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

    def import_workflow(self, workspace_path):
        """Import workflow from workspace to n8n"""
        workspace = Path(workspace_path)
        workflow_file = workspace / "workflow.json"

        if not workflow_file.exists():
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        # Load workflow JSON
        with open(workflow_file, 'r') as f:
            workflow_data = json.load(f)

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

            # Update metadata
            self.update_import_metadata(workspace, workflow_id, result)

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


def main():
    parser = argparse.ArgumentParser(description='Import workflow to n8n')
    parser.add_argument('--workspace', required=True, help='Path to workspace directory')
    parser.add_argument('--config', help='Path to config.json')
    parser.add_argument('--validate-only', action='store_true', help='Only validate, don\'t import')

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
        else:
            # Import workflow
            workflow_id = importer.import_workflow(args.workspace)
            return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())