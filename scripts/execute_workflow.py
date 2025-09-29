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
                },
                "debug": {
                    "log_level": "debug",
                    "capture_env": True,
                    "save_execution_data": True
                }
            }

    def check_workflow_active(self, workflow_id):
        """Check if workflow is active"""
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
            return workflow_data.get('active', False)
        except Exception as e:
            print(f"⚠️  Warning: Could not check workflow status: {e}")
            return False

    def activate_workflow(self, workflow_id):
        """Activate workflow if not already active"""
        base_url = self.config['n8n_api']['base_url']
        headers = {"Content-Type": "application/json"}

        # Add API key if configured
        api_key = self.config['n8n_api'].get('api_key')
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            # First, GET the current workflow data to check state
            get_url = f"{base_url}/api/v1/workflows/{workflow_id}"
            response = requests.get(get_url, headers=headers)
            response.raise_for_status()

            workflow_data = response.json()

            if workflow_data.get('active', False):
                return True  # Already active

            # Use the dedicated activate endpoint
            activate_url = f"{base_url}/api/v1/workflows/{workflow_id}/activate"
            print("🔄 Activating workflow...")

            # POST to the activation endpoint
            response = requests.post(activate_url, headers=headers)
            response.raise_for_status()

            # Verify the activation
            response = requests.get(get_url, headers=headers)
            response.raise_for_status()
            result = response.json()

            if result.get('active', False):
                print("✅ Workflow activated successfully")
                return True
            else:
                print("⚠️  Failed to activate workflow")
                return False

        except Exception as e:
            print(f"⚠️  Warning: Could not activate workflow: {e}")
            return False

    def execute_workflow(self, workspace_path, workflow_id, debug=False, method='auto', auto_activate=False, test_mode=False):
        """Execute workflow and capture all debug information"""
        workspace = Path(workspace_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Check and activate workflow if requested
        if auto_activate and method != 'webhook':
            # Check if workflow is active
            if not self.check_workflow_active(workflow_id):
                print("⚠️  Workflow is not active")
                if self.activate_workflow(workflow_id):
                    print("✅ Workflow has been activated")
                else:
                    print("⚠️  Could not activate workflow, continuing anyway...")

        # Create log files
        log_dir = workspace / "logs"
        log_dir.mkdir(exist_ok=True)

        execution_log = log_dir / f"execution_{timestamp}.log"
        error_log = log_dir / f"errors_{timestamp}.log"

        print(f"📝 Logging to: {execution_log.name}")

        # Determine execution method
        execution_result = None

        # Check if webhook method is requested or available
        if method == 'webhook' or method == 'auto':
            # Try to load webhook info from metadata
            metadata_file = workspace / "metadata.json"
            webhook_url = None

            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    webhook_config = metadata.get('webhook_config', {})

                    if webhook_config and 'webhooks' in webhook_config:
                        webhooks = webhook_config['webhooks']
                        if webhooks and len(webhooks) > 0:
                            # Use the first webhook found
                            webhook_info = webhooks[0]
                            webhook_url = webhook_info.get('production_url') or webhook_info.get('test_url')

                            if webhook_url and method == 'webhook':
                                print(f"🔗 Using webhook: {webhook_url}")

            # Try webhook execution if URL found
            if webhook_url:
                try:
                    execution_result = self.execute_via_webhook(
                        webhook_url,
                        execution_log,
                        error_log,
                        debug,
                        test_mode
                    )
                    if execution_result:
                        # Save and return if successful
                        if execution_result:
                            self.save_execution_data(workspace, timestamp, execution_result)
                        self.update_execution_metadata(workspace, timestamp, execution_result)
                        return execution_result
                except Exception as webhook_error:
                    print(f"⚠️  Webhook execution failed: {webhook_error}")
                    if method == 'webhook':
                        # If webhook was specifically requested, don't fallback
                        self.log_error(error_log, str(webhook_error))
                        raise

        # Try API execution if not webhook-only mode
        if method != 'webhook':
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

                if method != 'api':
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
                else:
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

    def execute_via_webhook(self, webhook_url, execution_log, error_log, debug=False, use_test_mode=False):
        """Execute workflow via webhook trigger"""
        start_time = datetime.now()

        # Import webhook manager for enhanced functionality
        from webhook_utils import WebhookManager
        webhook_mgr = WebhookManager()

        # Convert to test URL if requested
        if use_test_mode and '/webhook/' in webhook_url and '/webhook-test/' not in webhook_url:
            webhook_url = webhook_url.replace('/webhook/', '/webhook-test/')
            print(f"📝 Using test webhook URL: {webhook_url}")

        with open(execution_log, 'w') as log_file, open(error_log, 'w') as err_file:
            log_file.write(f"=== Webhook Workflow Execution ===\n")
            log_file.write(f"Timestamp: {start_time.isoformat()}\n")
            log_file.write(f"Webhook URL: {webhook_url}\n")
            log_file.write(f"Mode: {'Test' if use_test_mode else 'Production'}\n")
            log_file.write("=" * 50 + "\n\n")

            # Verify webhook registration first
            log_file.write("🔍 Verifying webhook registration...\n")
            verification = webhook_mgr.verify_webhook_registration(webhook_url)
            log_file.write(f"Registration status: {verification}\n\n")

            if not verification.get('registered') and not use_test_mode:
                log_file.write("⚠️  Webhook not registered, trying test mode instead...\n")
                webhook_url = webhook_url.replace('/webhook/', '/webhook-test/')
                use_test_mode = True

            try:
                # Prepare webhook payload
                payload = {
                    'trigger_source': 'n8n-integration',
                    'timestamp': start_time.isoformat(),
                    'debug_mode': debug,
                    'execution_type': 'webhook'
                }

                log_file.write("📤 Sending webhook request...\n")
                log_file.write(f"Payload: {json.dumps(payload, indent=2)}\n\n")

                # Send webhook request (using GET method as configured)
                # For GET request, pass data as query parameters
                response = requests.get(webhook_url, params={'data': json.dumps(payload)}, timeout=60)

                # Log response
                log_file.write(f"📥 Response Status: {response.status_code}\n")
                log_file.write(f"Response Headers: {dict(response.headers)}\n\n")

                if response.ok:
                    response_data = None
                    try:
                        response_data = response.json()
                        log_file.write("Response Data:\n")
                        log_file.write(json.dumps(response_data, indent=2))
                    except:
                        response_data = response.text
                        log_file.write(f"Response Text: {response_data}\n")

                    # Extract execution ID if available
                    execution_id = response.headers.get('x-n8n-execution-id', 'webhook-' + datetime.now().strftime("%Y%m%d%H%M%S"))

                    if debug:
                        print(f"✅ Webhook triggered successfully")
                        print(f"   Status: {response.status_code}")
                        if execution_id:
                            print(f"   Execution ID: {execution_id}")

                    return {
                        'execution_id': execution_id,
                        'status': 'success',
                        'duration': (datetime.now() - start_time).total_seconds(),
                        'webhook_url': webhook_url,
                        'response_status': response.status_code,
                        'data': response_data
                    }
                else:
                    error_msg = f"Webhook failed with status {response.status_code}: {response.text}"
                    log_file.write(f"\n❌ {error_msg}\n")
                    err_file.write(f"[{datetime.now().isoformat()}] {error_msg}\n")

                    return {
                        'execution_id': None,
                        'status': 'error',
                        'duration': (datetime.now() - start_time).total_seconds(),
                        'error': error_msg,
                        'response_status': response.status_code
                    }

            except requests.exceptions.Timeout:
                error_msg = "Webhook request timeout"
                log_file.write(f"\n❌ {error_msg}\n")
                err_file.write(f"[{datetime.now().isoformat()}] {error_msg}\n")
                raise Exception(error_msg)

            except Exception as e:
                error_msg = f"Webhook Execution Error: {str(e)}"
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
    parser.add_argument('--method', choices=['auto', 'api', 'cli', 'webhook'], default='auto',
                        help='Execution method (default: auto - tries webhook, then api, then cli)')
    parser.add_argument('--webhook-url', help='Override webhook URL for direct execution')
    parser.add_argument('--auto-activate', action='store_true',
                        help='Automatically activate workflow if inactive (not used for webhook method)')
    parser.add_argument('--test-mode', action='store_true',
                        help='Use test webhook mode (webhook-test URL) instead of production')

    args = parser.parse_args()

    try:
        executor = WorkflowExecutor(args.config)

        # If webhook URL provided directly, update method
        if args.webhook_url:
            args.method = 'webhook'
            # Temporarily store webhook URL in workspace metadata
            workspace = Path(args.workspace)
            metadata_file = workspace / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            else:
                metadata = {}

            metadata['webhook_config'] = {
                'webhooks': [{
                    'production_url': args.webhook_url,
                    'method': 'POST',
                    'node_name': 'Direct Webhook'
                }]
            }

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        result = executor.execute_workflow(
            args.workspace,
            args.workflow_id,
            args.debug,
            args.method,
            args.auto_activate,
            args.test_mode
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