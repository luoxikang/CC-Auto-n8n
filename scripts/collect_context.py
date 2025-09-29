#!/usr/bin/env python3
"""
Collect Context Script
Collects comprehensive debugging context and environment information
"""

import os
import json
import sys
import platform
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
import psutil
import socket


class ContextCollector:
    def __init__(self, workspace_path):
        """Initialize context collector with workspace path"""
        self.workspace = Path(workspace_path)
        self.context_dir = self.workspace / "context"
        self.context_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def collect_all(self):
        """Collect all context information"""
        print("📊 Collecting execution context...")

        context = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.collect_environment(),
            "system": self.collect_system_info(),
            "n8n": self.collect_n8n_info(),
            "workspace": self.collect_workspace_info(),
            "logs": self.analyze_recent_logs(),
            "errors": self.collect_recent_errors()
        }

        # Save complete context
        context_file = self.context_dir / f"debug_{self.timestamp}.json"
        with open(context_file, 'w') as f:
            json.dump(context, f, indent=2)

        print(f"✅ Context saved to: {context_file.name}")

        # Generate summary report
        self.generate_summary_report(context)

        return context

    def collect_environment(self):
        """Collect environment variables"""
        env_vars = {}

        # Relevant environment variables
        relevant_vars = [
            "N8N_HOST",
            "N8N_PORT",
            "N8N_PROTOCOL",
            "N8N_API_KEY",
            "N8N_BASIC_AUTH_ACTIVE",
            "N8N_LOG_LEVEL",
            "N8N_LOG_OUTPUT",
            "N8N_METRICS",
            "NODE_ENV",
            "PATH",
            "PYTHONPATH",
            "HOME",
            "USER"
        ]

        for var in relevant_vars:
            value = os.environ.get(var)
            if value:
                # Mask sensitive values
                if "KEY" in var or "PASSWORD" in var or "SECRET" in var:
                    env_vars[var] = "***MASKED***"
                else:
                    env_vars[var] = value

        # Add custom n8n variables
        for key, value in os.environ.items():
            if key.startswith("N8N_") and key not in env_vars:
                if "KEY" in key or "PASSWORD" in key or "SECRET" in key:
                    env_vars[key] = "***MASKED***"
                else:
                    env_vars[key] = value

        return env_vars

    def collect_system_info(self):
        """Collect system information"""
        try:
            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "hostname": socket.gethostname(),
                "cpu_count": psutil.cpu_count(),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent_used": psutil.virtual_memory().percent
                },
                "disk": {
                    "total": psutil.disk_usage('/').total,
                    "free": psutil.disk_usage('/').free,
                    "percent_used": psutil.disk_usage('/').percent
                }
            }
        except Exception as e:
            return {"error": f"Failed to collect system info: {str(e)}"}

    def collect_n8n_info(self):
        """Collect n8n specific information"""
        n8n_info = {}

        # Try to get n8n version
        try:
            result = subprocess.run(
                ["n8n", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                n8n_info["version"] = result.stdout.strip()
        except:
            n8n_info["version"] = "unknown"

        # Check if n8n is running
        try:
            # Check default port
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 5678))
            sock.close()
            n8n_info["is_running"] = (result == 0)
            n8n_info["default_port_open"] = (result == 0)
        except:
            n8n_info["is_running"] = False

        # Get configuration from config.json if exists
        config_path = self.workspace.parent / "config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    n8n_info["config"] = {
                        "base_url": config.get("n8n_api", {}).get("base_url"),
                        "has_api_key": bool(config.get("n8n_api", {}).get("api_key"))
                    }
            except:
                pass

        return n8n_info

    def collect_workspace_info(self):
        """Collect workspace information"""
        info = {
            "path": str(self.workspace),
            "workflow_exists": (self.workspace / "workflow.json").exists()
        }

        # Get workflow info if exists
        workflow_file = self.workspace / "workflow.json"
        if workflow_file.exists():
            try:
                with open(workflow_file, 'r') as f:
                    workflow = json.load(f)
                    info["workflow"] = {
                        "name": workflow.get("name", "Unknown"),
                        "node_count": len(workflow.get("nodes", [])),
                        "has_credentials": any(
                            node.get("credentials")
                            for node in workflow.get("nodes", [])
                        ),
                        "node_types": list(set(
                            node.get("type", "unknown")
                            for node in workflow.get("nodes", [])
                        ))
                    }
            except Exception as e:
                info["workflow_error"] = str(e)

        # Get metadata info
        metadata_file = self.workspace / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    info["metadata"] = {
                        "workflow_id": metadata.get("workflow_id"),
                        "last_execution": metadata.get("last_execution"),
                        "version_count": metadata.get("version_count", 0)
                    }
            except:
                pass

        # Count files in directories
        info["file_counts"] = {
            "logs": len(list((self.workspace / "logs").glob("*.log")))
            if (self.workspace / "logs").exists() else 0,
            "context": len(list((self.workspace / "context").glob("*.json")))
            if (self.workspace / "context").exists() else 0,
            "versions": len(list((self.workspace / "versions").glob("*.json")))
            if (self.workspace / "versions").exists() else 0
        }

        return info

    def analyze_recent_logs(self):
        """Analyze recent log files for patterns"""
        logs_dir = self.workspace / "logs"
        if not logs_dir.exists():
            return {"message": "No logs directory found"}

        # Get most recent execution log
        log_files = sorted(
            logs_dir.glob("execution_*.log"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        if not log_files:
            return {"message": "No execution logs found"}

        recent_log = log_files[0]
        analysis = {
            "recent_log": recent_log.name,
            "size_bytes": recent_log.stat().st_size,
            "modified": datetime.fromtimestamp(recent_log.stat().st_mtime).isoformat()
        }

        # Analyze log content
        try:
            with open(recent_log, 'r') as f:
                content = f.read()

                # Count occurrences of key patterns
                analysis["patterns"] = {
                    "errors": content.count("ERROR") + content.count("error"),
                    "warnings": content.count("WARNING") + content.count("warning"),
                    "success": content.count("SUCCESS") + content.count("success"),
                    "failed": content.count("FAILED") + content.count("failed"),
                    "node_executions": content.count("Node:"),
                    "api_calls": content.count("API")
                }

                # Extract last few lines for quick review
                lines = content.split('\n')
                analysis["last_10_lines"] = lines[-10:] if len(lines) > 10 else lines

        except Exception as e:
            analysis["read_error"] = str(e)

        return analysis

    def collect_recent_errors(self):
        """Collect recent errors from error logs"""
        logs_dir = self.workspace / "logs"
        if not logs_dir.exists():
            return []

        error_files = sorted(
            logs_dir.glob("errors_*.log"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        errors = []
        for error_file in error_files[:3]:  # Last 3 error files
            try:
                with open(error_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        errors.append({
                            "file": error_file.name,
                            "timestamp": datetime.fromtimestamp(
                                error_file.stat().st_mtime
                            ).isoformat(),
                            "content": content[:1000]  # First 1000 chars
                        })
            except:
                continue

        return errors

    def generate_summary_report(self, context):
        """Generate a human-readable summary report"""
        report_file = self.context_dir / f"summary_{self.timestamp}.txt"

        with open(report_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("N8N WORKFLOW DEBUG CONTEXT SUMMARY\n")
            f.write("=" * 60 + "\n\n")

            # Timestamp
            f.write(f"Generated: {context['timestamp']}\n")
            f.write(f"Workspace: {self.workspace.name}\n\n")

            # System Info
            f.write("SYSTEM INFORMATION\n")
            f.write("-" * 40 + "\n")
            sys_info = context.get('system', {})
            f.write(f"Platform: {sys_info.get('platform', 'Unknown')}\n")
            f.write(f"Python: {sys_info.get('python_version', 'Unknown').split()[0]}\n")
            f.write(f"Memory Used: {sys_info.get('memory', {}).get('percent_used', 0):.1f}%\n\n")

            # n8n Info
            f.write("N8N STATUS\n")
            f.write("-" * 40 + "\n")
            n8n_info = context.get('n8n', {})
            f.write(f"Version: {n8n_info.get('version', 'Unknown')}\n")
            f.write(f"Running: {'Yes' if n8n_info.get('is_running') else 'No'}\n")
            if 'config' in n8n_info:
                f.write(f"API URL: {n8n_info['config'].get('base_url', 'Not configured')}\n")
            f.write("\n")

            # Workflow Info
            f.write("WORKFLOW INFORMATION\n")
            f.write("-" * 40 + "\n")
            workspace_info = context.get('workspace', {})
            if 'workflow' in workspace_info:
                wf = workspace_info['workflow']
                f.write(f"Name: {wf.get('name', 'Unknown')}\n")
                f.write(f"Nodes: {wf.get('node_count', 0)}\n")
                f.write(f"Node Types: {', '.join(wf.get('node_types', []))}\n")
            if 'metadata' in workspace_info:
                meta = workspace_info['metadata']
                if 'last_execution' in meta and meta['last_execution']:
                    f.write(f"\nLast Execution:\n")
                    f.write(f"  Status: {meta['last_execution'].get('status', 'Unknown')}\n")
                    f.write(f"  Duration: {meta['last_execution'].get('duration', 0):.2f}s\n")
            f.write("\n")

            # Recent Logs Analysis
            f.write("LOG ANALYSIS\n")
            f.write("-" * 40 + "\n")
            logs = context.get('logs', {})
            if 'patterns' in logs:
                patterns = logs['patterns']
                f.write(f"Errors: {patterns.get('errors', 0)}\n")
                f.write(f"Warnings: {patterns.get('warnings', 0)}\n")
                f.write(f"Failures: {patterns.get('failed', 0)}\n")
                f.write(f"Node Executions: {patterns.get('node_executions', 0)}\n")
            f.write("\n")

            # Recent Errors
            errors = context.get('errors', [])
            if errors:
                f.write("RECENT ERRORS\n")
                f.write("-" * 40 + "\n")
                for error in errors[:2]:
                    f.write(f"From: {error['file']}\n")
                    f.write(f"Time: {error['timestamp']}\n")
                    f.write(f"Error: {error['content'][:200]}...\n\n")

            # File Counts
            f.write("FILE STATISTICS\n")
            f.write("-" * 40 + "\n")
            file_counts = workspace_info.get('file_counts', {})
            f.write(f"Log Files: {file_counts.get('logs', 0)}\n")
            f.write(f"Context Files: {file_counts.get('context', 0)}\n")
            f.write(f"Version Backups: {file_counts.get('versions', 0)}\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("Full context saved in: debug_" + self.timestamp + ".json\n")
            f.write("=" * 60 + "\n")

        print(f"📄 Summary report: {report_file.name}")


def main():
    parser = argparse.ArgumentParser(description='Collect execution context')
    parser.add_argument('--workspace', required=True, help='Path to workspace directory')
    parser.add_argument('--minimal', action='store_true',
                        help='Collect minimal context only')

    args = parser.parse_args()

    try:
        collector = ContextCollector(args.workspace)
        context = collector.collect_all()

        print("✅ Context collection completed")
        return 0

    except Exception as e:
        print(f"❌ Context collection failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())