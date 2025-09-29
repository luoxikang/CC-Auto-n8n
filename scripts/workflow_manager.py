#!/usr/bin/env python3
"""
Workflow Manager for n8n Integration
Manages workspace creation, versioning, and workflow lifecycle
"""

import os
import json
import shutil
import argparse
import re
from datetime import datetime
from pathlib import Path
import subprocess
import sys


class WorkflowManager:
    def __init__(self, base_dir=None):
        """Initialize the workflow manager with base directory"""
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.workflows_dir = self.base_dir / "workflows"
        self.config_path = self.base_dir / "config.json"

        # Ensure base directories exist
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

        # Load config if exists
        self.config = self.load_config()

    def load_config(self):
        """Load configuration from config.json"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {
            "n8n_api": {
                "base_url": "http://localhost:5678",
                "api_key": ""
            },
            "debug": {
                "log_level": "debug",
                "capture_env": True,
                "save_execution_data": True
            }
        }

    def normalize_workflow_name(self, json_path):
        """Extract and normalize workflow name from JSON file path"""
        filename = Path(json_path).stem
        # Remove special characters and normalize
        normalized = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
        normalized = re.sub(r'_+', '_', normalized).strip('_')
        return normalized.lower()

    def setup_workspace(self, json_path):
        """
        Set up or update workspace for a workflow
        Returns: workspace path
        """
        json_path = Path(json_path)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")

        # Get workflow name
        workflow_name = self.normalize_workflow_name(json_path)
        workspace_path = self.workflows_dir / workflow_name

        # Check if workspace exists
        is_new = not workspace_path.exists()

        # Create directory structure
        (workspace_path / "logs").mkdir(parents=True, exist_ok=True)
        (workspace_path / "context").mkdir(parents=True, exist_ok=True)
        (workspace_path / "versions").mkdir(parents=True, exist_ok=True)

        # Handle workflow.json
        target_workflow_path = workspace_path / "workflow.json"

        if not is_new and target_workflow_path.exists():
            # Backup existing workflow
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = workspace_path / "versions" / f"v{timestamp}_workflow.json"
            shutil.copy2(target_workflow_path, backup_path)
            print(f"📦 Backed up existing workflow to: {backup_path.relative_to(self.base_dir)}")

        # Copy new workflow
        shutil.copy2(json_path, target_workflow_path)

        # Create/Update metadata
        self.update_metadata(workspace_path, workflow_name, is_new)

        action = "Created new" if is_new else "Updated existing"
        print(f"✅ {action} workspace: {workspace_path.relative_to(self.base_dir)}")

        return str(workspace_path)

    def update_metadata(self, workspace_path, workflow_name, is_new=False):
        """Create or update metadata.json"""
        metadata_path = workspace_path / "metadata.json"

        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {
                "workflow_name": workflow_name,
                "created_at": datetime.now().isoformat()
            }

        # Update metadata
        metadata["last_modified"] = datetime.now().isoformat()

        # Count versions
        versions_dir = workspace_path / "versions"
        if versions_dir.exists():
            metadata["version_count"] = len(list(versions_dir.glob("v*_workflow.json")))

        # Analyze workflow
        workflow_path = workspace_path / "workflow.json"
        if workflow_path.exists():
            with open(workflow_path, 'r') as f:
                workflow_data = json.load(f)
                metadata["n8n_config"] = {
                    "node_count": len(workflow_data.get("nodes", [])),
                    "has_credentials": any(
                        node.get("credentials")
                        for node in workflow_data.get("nodes", [])
                    )
                }

        # Save metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def list_workspaces(self):
        """List all available workspaces"""
        workspaces = []
        for workspace_dir in self.workflows_dir.iterdir():
            if workspace_dir.is_dir():
                metadata_path = workspace_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        workspaces.append({
                            "name": workspace_dir.name,
                            "path": str(workspace_dir),
                            "last_modified": metadata.get("last_modified", "Unknown"),
                            "version_count": metadata.get("version_count", 0)
                        })
        return workspaces

    def get_workspace_path(self, workflow_name):
        """Get workspace path for a workflow name"""
        workspace_path = self.workflows_dir / workflow_name
        if not workspace_path.exists():
            raise ValueError(f"Workspace not found: {workflow_name}")
        return str(workspace_path)

    def cleanup_old_logs(self, workflow_name, keep_last=5):
        """Clean up old logs, keeping only the most recent ones"""
        workspace_path = Path(self.get_workspace_path(workflow_name))
        logs_dir = workspace_path / "logs"

        if not logs_dir.exists():
            return

        # Get all log files sorted by modification time
        log_files = sorted(
            logs_dir.glob("*.log"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        # Remove old files
        for log_file in log_files[keep_last:]:
            log_file.unlink()
            print(f"🗑️  Removed old log: {log_file.name}")

    def run_workflow(self, workflow_name, debug=False):
        """Execute complete workflow cycle: import, execute, collect context"""
        workspace_path = Path(self.get_workspace_path(workflow_name))
        scripts_dir = self.base_dir / "scripts"

        print(f"\n🚀 Running workflow: {workflow_name}")
        print("=" * 50)

        # 1. Import workflow
        print("\n📥 Importing workflow to n8n...")
        result = subprocess.run(
            [sys.executable, str(scripts_dir / "import_workflow.py"),
             "--workspace", str(workspace_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"❌ Import failed: {result.stderr}")
            return False

        # Extract workflow ID from output
        workflow_id = None
        for line in result.stdout.split('\n'):
            if 'workflow_id' in line:
                workflow_id = line.split(':')[-1].strip()

        if not workflow_id:
            print("❌ Could not get workflow ID")
            return False

        print(f"✅ Imported with ID: {workflow_id}")

        # 2. Execute workflow
        print("\n⚡ Executing workflow...")
        cmd = [sys.executable, str(scripts_dir / "execute_workflow.py"),
               "--workspace", str(workspace_path),
               "--workflow-id", workflow_id]

        if debug:
            cmd.append("--debug")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"⚠️  Execution completed with errors")
        else:
            print(f"✅ Execution completed successfully")

        # 3. Collect context
        print("\n📊 Collecting execution context...")
        subprocess.run(
            [sys.executable, str(scripts_dir / "collect_context.py"),
             "--workspace", str(workspace_path)],
            capture_output=False
        )

        # Show results location
        print("\n📁 Results saved in:")
        print(f"   Logs: {workspace_path / 'logs'}")
        print(f"   Context: {workspace_path / 'context'}")

        return True

    def debug_cycle(self, json_path, auto_fix=False, max_iterations=3):
        """
        Complete debug cycle with optional auto-fix
        """
        # Setup workspace
        workspace_path = self.setup_workspace(json_path)
        workflow_name = Path(workspace_path).name

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            print(f"\n🔄 Debug iteration {iteration}/{max_iterations}")

            # Run workflow
            success = self.run_workflow(workflow_name, debug=True)

            if success and not auto_fix:
                print("\n✅ Workflow executed successfully!")
                break

            if auto_fix and iteration < max_iterations:
                print("\n🔧 Analyzing logs for auto-fix...")
                # Here Claude Code would analyze logs and modify workflow.json
                print("⏸️  Waiting for Claude Code to analyze and fix...")
                input("Press Enter after fixes are applied...")
            else:
                break

        # Cleanup old logs
        self.cleanup_old_logs(workflow_name)

        print(f"\n🏁 Debug cycle completed after {iteration} iteration(s)")


def main():
    parser = argparse.ArgumentParser(description='n8n Workflow Manager')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup workspace for a workflow')
    setup_parser.add_argument('--json', required=True, help='Path to workflow JSON file')

    # List command
    list_parser = subparsers.add_parser('list', help='List all workspaces')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run a workflow')
    run_parser.add_argument('--name', required=True, help='Workflow name')
    run_parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    # Debug command
    debug_parser = subparsers.add_parser('debug', help='Debug cycle for a workflow')
    debug_parser.add_argument('--json', required=True, help='Path to workflow JSON file')
    debug_parser.add_argument('--auto-fix', action='store_true', help='Enable auto-fix mode')
    debug_parser.add_argument('--max-iterations', type=int, default=3, help='Max debug iterations')

    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean old logs')
    cleanup_parser.add_argument('--name', required=True, help='Workflow name')
    cleanup_parser.add_argument('--keep', type=int, default=5, help='Number of logs to keep')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    manager = WorkflowManager()

    try:
        if args.command == 'setup':
            manager.setup_workspace(args.json)

        elif args.command == 'list':
            workspaces = manager.list_workspaces()
            if workspaces:
                print("\n📁 Available Workspaces:")
                print("-" * 60)
                for ws in workspaces:
                    print(f"  • {ws['name']}")
                    print(f"    Last modified: {ws['last_modified']}")
                    print(f"    Versions: {ws['version_count']}")
            else:
                print("No workspaces found")

        elif args.command == 'run':
            manager.run_workflow(args.name, args.debug)

        elif args.command == 'debug':
            manager.debug_cycle(args.json, args.auto_fix, args.max_iterations)

        elif args.command == 'cleanup':
            manager.cleanup_old_logs(args.name, args.keep)
            print(f"✅ Cleaned up logs for {args.name}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())