#!/usr/bin/env python3
"""
Execute Workflow Script
Executes workflow in n8n and captures complete debug information
"""

import os
import json
import argparse
import requests
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time


class WorkflowExecutor:
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
                },
                "debug": {
                    "log_level": "debug",
                    "capture_env": True,
                    "save_execution_data": True
                }
            }

    def execute_workflow(self, workspace_path, workflow_id, debug=False):
        """Execute workflow and capture all debug information"""
        workspace = Path(workspace_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create log files
        log_dir = workspace / "logs"
        log_dir.mkdir(exist_ok=True)

        execution_log = log_dir / f"execution_{timestamp}.log"
        error_log = log_dir / f"errors_{timestamp}.log"

        print(f"📝 Logging to: {execution_log.name}")

        # Determine execution method
        execution_result = None

        try:
            # Try API execution first
            execution_result = self.execute_via_api(
                workflow_id,
                execution_log,
                error_log,
                debug
            )
        except Exception as api_error:
            print(f"⚠️  API execution failed: {api_error}")
            print("🔄 Attempting CLI execution...")

            # Fallback to CLI execution
            try:
                execution_result = self.execute_via_cli(
                    workflow_id,
                    execution_log,
                    error_log,
                    debug
                )
            except Exception as cli_error:
                print(f"❌ CLI execution also failed: {cli_error}")
                self.log_error(error_log, str(cli_error))
                raise

        # Save execution result
        if execution_result:
            self.save_execution_data(workspace, timestamp, execution_result)

        # Update metadata with execution info
        self.update_execution_metadata(workspace, timestamp, execution_result)

        return execution_result

    def execute_via_api(self, workflow_id, execution_log, error_log, debug=False):
        """Execute workflow via n8n API"""
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/executions"
        headers = {
            "Content-Type": "application/json"
        }

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        # Prepare execution request
        execution_data = {
            "workflowId": workflow_id
        }

        # Start execution
        start_time = datetime.now()

        with open(execution_log, 'w') as log_file:
            log_file.write(f"=== Workflow Execution Started ===\n")
            log_file.write(f"Timestamp: {start_time.isoformat()}\n")
            log_file.write(f"Workflow ID: {workflow_id}\n")
            log_file.write(f"API URL: {self.config['n8n_api']['base_url']}\n")
            log_file.write(f"Debug Mode: {debug}\n")
            log_file.write("=" * 50 + "\n\n")

            try:
                # Start workflow execution
                response = requests.post(
                    f"{self.config['n8n_api']['base_url']}/api/v1/workflows/{workflow_id}/execute",
                    headers=headers,
                    json=execution_data
                )
                response.raise_for_status()

                execution = response.json()
                execution_id = execution.get('id')

                log_file.write(f"Execution ID: {execution_id}\n")
                log_file.write(f"Status: Started\n\n")

                # Poll for execution status
                status = self.poll_execution_status(execution_id, log_file, debug)

                # Get full execution data
                if status in ['success', 'error']:
                    execution_detail = self.get_execution_detail(execution_id)

                    # Log execution results
                    log_file.write("\n=== Execution Results ===\n")
                    log_file.write(json.dumps(execution_detail, indent=2))
                    log_file.write("\n\n")

                    # Process node outputs if debug enabled
                    if debug and 'data' in execution_detail:
                        self.log_node_outputs(log_file, execution_detail['data'])

                    # Log any errors
                    if status == 'error' and 'error' in execution_detail:
                        self.log_error(error_log, json.dumps(execution_detail['error'], indent=2))

                    return {
                        'execution_id': execution_id,
                        'status': status,
                        'duration': (datetime.now() - start_time).total_seconds(),
                        'data': execution_detail
                    }

            except Exception as e:
                error_msg = f"API Execution Error: {str(e)}"
                log_file.write(f"\n❌ {error_msg}\n")
                self.log_error(error_log, error_msg)
                raise

            finally:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                log_file.write(f"\n=== Execution Completed ===\n")
                log_file.write(f"End Time: {end_time.isoformat()}\n")
                log_file.write(f"Duration: {duration:.2f} seconds\n")

    def execute_via_cli(self, workflow_id, execution_log, error_log, debug=False):
        """Execute workflow via n8n CLI"""
        start_time = datetime.now()

        # Construct CLI command
        cmd = ["n8n", "execute", "--id", workflow_id]

        if debug:
            cmd.extend(["--log-level", "debug"])

        with open(execution_log, 'w') as log_file, open(error_log, 'w') as err_file:
            log_file.write(f"=== CLI Workflow Execution ===\n")
            log_file.write(f"Timestamp: {start_time.isoformat()}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write("=" * 50 + "\n\n")

            try:
                # Execute command
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env={**os.environ, "N8N_LOG_LEVEL": "debug"} if debug else os.environ
                )

                # Capture output in real-time
                for line in iter(process.stdout.readline, ''):
                    if line:
                        log_file.write(line)
                        log_file.flush()
                        if debug:
                            print(f"  {line.strip()}")

                # Wait for completion
                process.wait()

                # Capture any errors
                stderr_output = process.stderr.read()
                if stderr_output:
                    err_file.write(stderr_output)

                # Determine status
                status = "success" if process.returncode == 0 else "error"

                return {
                    'execution_method': 'cli',
                    'status': status,
                    'return_code': process.returncode,
                    'duration': (datetime.now() - start_time).total_seconds()
                }

            except Exception as e:
                error_msg = f"CLI Execution Error: {str(e)}"
                err_file.write(error_msg)
                raise

    def poll_execution_status(self, execution_id, log_file, debug=False):
        """Poll execution status until completion"""
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/executions/{execution_id}"
        headers = {}

        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        max_polls = 60  # Maximum 60 seconds
        poll_interval = 1  # Check every second

        for i in range(max_polls):
            try:
                response = requests.get(api_url, headers=headers)
                response.raise_for_status()

                execution = response.json()
                status = execution.get('finished', False)
                has_error = execution.get('stoppedAt') is not None and 'error' in execution

                if debug and i % 5 == 0:  # Log every 5 seconds in debug mode
                    log_file.write(f"Poll {i+1}: Status check...\n")

                if status or has_error:
                    final_status = 'error' if has_error else 'success'
                    log_file.write(f"Execution completed with status: {final_status}\n")
                    return final_status

                time.sleep(poll_interval)

            except Exception as e:
                log_file.write(f"Error polling status: {e}\n")
                return 'unknown'

        log_file.write("Execution timed out\n")
        return 'timeout'

    def get_execution_detail(self, execution_id):
        """Get detailed execution data"""
        api_url = f"{self.config['n8n_api']['base_url']}/api/v1/executions/{execution_id}"
        headers = {}

        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}

    def log_node_outputs(self, log_file, execution_data):
        """Log individual node outputs in debug mode"""
        log_file.write("\n=== Node Outputs ===\n")

        if isinstance(execution_data, dict):
            for node_name, node_data in execution_data.items():
                log_file.write(f"\n📦 Node: {node_name}\n")
                log_file.write("-" * 40 + "\n")

                if isinstance(node_data, list) and len(node_data) > 0:
                    for i, output in enumerate(node_data):
                        log_file.write(f"Output {i+1}:\n")
                        log_file.write(json.dumps(output, indent=2))
                        log_file.write("\n")
                else:
                    log_file.write("No output data\n")

    def log_error(self, error_log_path, error_message):
        """Log error to error file"""
        with open(error_log_path, 'a') as f:
            f.write(f"\n[{datetime.now().isoformat()}] {error_message}\n")

    def save_execution_data(self, workspace, timestamp, execution_result):
        """Save complete execution data for analysis"""
        context_dir = workspace / "context"
        context_dir.mkdir(exist_ok=True)

        execution_file = context_dir / f"execution_{timestamp}.json"

        # Add environment context if configured
        if self.config['debug'].get('capture_env'):
            execution_result['environment'] = {
                'n8n_url': self.config['n8n_api']['base_url'],
                'timestamp': timestamp,
                'debug_enabled': self.config['debug'].get('log_level') == 'debug'
            }

        with open(execution_file, 'w') as f:
            json.dump(execution_result, f, indent=2)

    def update_execution_metadata(self, workspace, timestamp, execution_result):
        """Update metadata with latest execution info"""
        metadata_path = workspace / "metadata.json"

        metadata = {}
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

        # Update execution info
        metadata['last_execution'] = {
            'timestamp': timestamp,
            'status': execution_result.get('status', 'unknown'),
            'duration': execution_result.get('duration', 0),
            'log_file': f"logs/execution_{timestamp}.log"
        }

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Execute n8n workflow')
    parser.add_argument('--workspace', required=True, help='Path to workspace directory')
    parser.add_argument('--workflow-id', required=True, help='Workflow ID to execute')
    parser.add_argument('--config', help='Path to config.json')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--method', choices=['api', 'cli'], default='api',
                        help='Execution method (default: api)')

    args = parser.parse_args()

    try:
        executor = WorkflowExecutor(args.config)
        result = executor.execute_workflow(
            args.workspace,
            args.workflow_id,
            args.debug
        )

        if result and result.get('status') == 'success':
            print("✅ Workflow executed successfully")
            return 0
        else:
            print("⚠️  Workflow execution completed with warnings or errors")
            return 1

    except Exception as e:
        print(f"❌ Execution failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())