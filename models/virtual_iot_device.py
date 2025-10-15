# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import logging
import secrets

_logger = logging.getLogger(__name__)


class VirtualIoTDevice(models.Model):
    _name = 'virtual.iot.device'
    _description = 'Virtual IoT Device'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Device Name',
        required=True,
        help='Name of the Virtual IoT device'
    )
    
    ip_address = fields.Char(
        string='IP Address',
        required=True,
        help='IP address or domain name where the Virtual IoT service is running'
    )
    
    port = fields.Char(
        string='Port',
        default='8000',
        help='Port number for the Virtual IoT service'
    )
    
    api_key = fields.Char(
        string='API Key',
        required=True,
        default=lambda self: self._generate_api_key(),
        help='API key for secure communication'
    )
    
    api_key_hash = fields.Char('API Key Hash', readonly=True)
    
    # Security settings
    allowed_ip_addresses = fields.Text('Allowed IP Addresses', 
                                      help='One per line. Leave empty to allow all IPs.')
    rate_limit_enabled = fields.Boolean('Rate Limiting Enabled', default=True)
    rate_limit_requests = fields.Integer('Requests per Minute', default=60)
    last_activity = fields.Datetime('Last Activity', readonly=True)
    failed_auth_attempts = fields.Integer('Failed Auth Attempts', default=0, readonly=True)
    blocked_until = fields.Datetime('Blocked Until', readonly=True)
    
    status = fields.Selection([
        ('offline', 'Offline'),
        ('online', 'Online'),
        ('error', 'Error')
    ], string='Status', default='offline', readonly=True)
    
    last_seen = fields.Datetime(
        string='Last Seen',
        readonly=True,
        help='Last time the device was seen online'
    )
    
    printer_ids = fields.One2many(
        'virtual.iot.printer',
        'device_id',
        string='Printers',
        help='Printers connected to this device'
    )
    
    print_job_ids = fields.One2many(
        'virtual.iot.print.job',
        'device_id',
        string='Print Jobs',
        help='Print jobs sent to this device'
    )
    
    security_log_ids = fields.One2many(
        'virtual.iot.security.log',
        'device_id',
        string='Security Logs'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    use_https = fields.Boolean(
        string='Use HTTPS',
        default=False,
        help='Use HTTPS for secure communication'
    )
    
    @api.model
    def _generate_api_key(self):
        """Generate a secure API key"""
        security_util = self.env['virtual.iot.security']
        return security_util.generate_api_key()
    
    @api.constrains('ip_address')
    def _check_ip_address(self):
        """Validate IP address or domain name format"""
        import re
        for record in self:
            if record.ip_address:
                # IP address pattern (IPv4)
                ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
                # Domain name pattern (including subdomains)
                domain_pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'
                # localhost pattern
                localhost_pattern = r'^localhost$'
                
                if not (re.match(ip_pattern, record.ip_address) or 
                       re.match(domain_pattern, record.ip_address) or 
                       re.match(localhost_pattern, record.ip_address)):
                    raise ValidationError(_('Invalid IP address or domain name format'))
    
    @api.constrains('port')
    def _check_port(self):
        """Validate port number"""
        for record in self:
            if record.port:
                try:
                    port_int = int(record.port)
                    if port_int < 1 or port_int > 65535:
                        raise ValidationError(_('Port must be between 1 and 65535'))
                except ValueError:
                    raise ValidationError(_('Port must be a valid number'))
    
    def _get_base_url(self):
        """Get the base URL for the Virtual IoT service"""
        self.ensure_one()
        protocol = 'https' if self.use_https else 'http'
        return f"{protocol}://{self.ip_address}:{self.port}"
    
    def _get_headers(self):
        """Get headers for API requests"""
        self.ensure_one()
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def test_connection(self):
        """Test connection to the Virtual IoT service"""
        self.ensure_one()
        try:
            url = self._get_base_url()
            response = requests.get(url, headers=self._get_headers(), timeout=5)
            
            if response.status_code == 200:
                self.status = 'online'
                self.last_seen = fields.Datetime.now()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': _('Successfully connected to %s') % self.name,
                        'type': 'success',
                    }
                }
            else:
                self.status = 'error'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': _('Failed to connect to %s (Status: %s)') % (self.name, response.status_code),
                        'type': 'warning',
                    }
                }
        except Exception as e:
            self.status = 'error'
            _logger.error(f"Connection test failed for device {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': _('Connection failed: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def sync_printers(self):
        """Sync printers from the Virtual IoT service"""
        self.ensure_one()
        try:
            url = f"{self._get_base_url()}/printers"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            
            if response.status_code == 200:
                printers_data = response.json()
                
                # Get existing printers to preserve their configuration
                existing_printers = {printer.name: printer for printer in self.printer_ids}
                synced_printer_names = set()
                
                # Update or create printer records
                for printer_data in printers_data:
                    printer_name = printer_data.get('name')
                    synced_printer_names.add(printer_name)
                    
                    # Prepare printer values with connection information
                    printer_values = {
                        'status': 'ready',
                        'active': True,
                        'connection_type': printer_data.get('connection_type', 'network'),
                        'device_path': printer_data.get('device_path', ''),
                        'ip_address': printer_data.get('ip_address', ''),
                        'port': printer_data.get('port', 631),
                    }
                    
                    if printer_name in existing_printers:
                        # Update existing printer (preserve manual configuration like printer_type)
                        existing_printer = existing_printers[printer_name]
                        existing_printer.write(printer_values)
                    else:
                        # Create new printer record
                        printer_values.update({
                            'name': printer_name,
                            'printer_type': printer_data.get('type', 'receipt'),
                            'device_id': self.id,
                        })
                        self.env['virtual.iot.printer'].create(printer_values)
                
                # Mark printers not found in sync as offline (don't delete them)
                offline_count = 0
                for printer_name, printer in existing_printers.items():
                    if printer_name not in synced_printer_names:
                        if printer.status != 'offline':
                            printer.write({'status': 'offline'})
                            _logger.info(f"Printer {printer_name} marked as offline - not found in sync")
                            offline_count += 1
                
                self.status = 'online'
                self.last_seen = fields.Datetime.now()
                
                # Prepare success message
                message = _('Successfully synced %d printers') % len(printers_data)
                if offline_count > 0:
                    message += _(', %d printers marked as offline') % offline_count
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Printer Sync'),
                        'message': message,
                        'type': 'success',
                    }
                }
            else:
                self.status = 'error'
                # Mark all printers as offline when device has error
                self.printer_ids.write({'status': 'offline'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Printer Sync'),
                        'message': _('Failed to sync printers (Status: %s)') % response.status_code,
                        'type': 'warning',
                    }
                }
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            self.status = 'offline'
            # Mark all printers as offline when device is unreachable
            self.printer_ids.write({'status': 'offline'})
            _logger.warning(f"Device {self.name} is unreachable during sync: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Printer Sync'),
                    'message': _('Device unreachable: %s') % str(e),
                    'type': 'warning',
                }
            }
        except Exception as e:
            self.status = 'error'
            # Mark all printers as offline on unexpected error
            self.printer_ids.write({'status': 'offline'})
            _logger.error(f"Printer sync failed for device {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Printer Sync'),
                    'message': _('Sync failed: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    @api.model
    def register_device(self, name, ip_address, port='8000', api_key=None):
        """Register a new Virtual IoT device"""
        if not api_key:
            api_key = self._generate_api_key()
        
        # Check if device already exists
        existing_device = self.search([
            ('ip_address', '=', ip_address),
            ('port', '=', str(port))
        ], limit=1)
        
        if existing_device:
            # Update existing device
            existing_device.write({
                'name': name,
                'api_key': api_key,
                'status': 'online',
                'last_seen': fields.Datetime.now()
            })
            return existing_device
        else:
            # Create new device
            return self.create({
                'name': name,
                'ip_address': ip_address,
                'port': port,
                'api_key': api_key,
                'status': 'online',
                'last_seen': fields.Datetime.now()
            })
    
    def _hash_api_key(self, api_key):
        """Hash API key for secure storage"""
        security_util = self.env['virtual.iot.security']
        return security_util.hash_api_key(api_key)
    
    def verify_api_key(self, api_key):
        """Verify API key against stored hash"""
        if not self.api_key_hash:
            return False
        security_util = self.env['virtual.iot.security']
        return security_util.verify_api_key(api_key, self.api_key_hash)
    
    def check_ip_access(self, ip_address):
        """Check if IP address is allowed"""
        if not self.allowed_ip_addresses:
            return True
        
        allowed_ips = [ip.strip() for ip in self.allowed_ip_addresses.split('\n') if ip.strip()]
        security_util = self.env['virtual.iot.security']
        return security_util.validate_ip_address(ip_address, allowed_ips)
    
    def is_blocked(self):
        """Check if device is currently blocked due to failed auth attempts"""
        if not self.blocked_until:
            return False
        return fields.Datetime.now() < self.blocked_until
    
    def record_failed_auth(self, ip_address=None):
        """Record a failed authentication attempt"""
        self.failed_auth_attempts += 1
        
        # Block device after 5 failed attempts for 15 minutes
        if self.failed_auth_attempts >= 5:
            from datetime import timedelta
            self.blocked_until = fields.Datetime.now() + timedelta(minutes=15)
        
        # Log security event
        security_util = self.env['virtual.iot.security']
        security_util.log_security_event(
            'unauthorized_access',
            f'Failed authentication attempt for device {self.name} from IP {ip_address or "unknown"}',
            device_id=self.id,
            ip_address=ip_address
        )
    
    def record_successful_auth(self):
        """Record a successful authentication"""
        self.last_activity = fields.Datetime.now()
        self.failed_auth_attempts = 0
        self.blocked_until = False
    
    def regenerate_api_key(self):
        """Regenerate API key for the device"""
        self.ensure_one()
        
        # Check if auto-sync is enabled
        auto_sync_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'virtual_iot.auto_sync_enabled', 'True'
        ).lower() == 'true'
        
        fallback_to_manual = self.env['ir.config_parameter'].sudo().get_param(
            'virtual_iot.fallback_to_manual', 'True'
        ).lower() == 'true'
        
        old_key = self.api_key
        new_key = self._generate_api_key()
        sync_success = False
        
        if auto_sync_enabled:
            # Try to sync with Virtual IoT Service first
            sync_success = self._sync_api_key_with_service(old_key, new_key)
        
        if sync_success:
            # Update Odoo database only if sync was successful
            self.api_key = new_key
            self.api_key_hash = self._hash_api_key(new_key)
            
            # Log security event
            security_util = self.env['virtual.iot.security']
            security_util.log_security_event(
                'api_key_regenerated',
                f'API key regenerated and synced for device {self.name} (ID: {self.id})',
                device_id=self.id
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('API Key Regenerated'),
                    'message': _('New API key has been generated and automatically synced with device %s') % self.name,
                    'type': 'success',
                }
            }
        elif fallback_to_manual or not auto_sync_enabled:
            # Fallback to manual process if auto-sync fails or is disabled
            self.api_key = new_key
            self.api_key_hash = self._hash_api_key(new_key)
            
            # Log security event with appropriate message
            security_util = self.env['virtual.iot.security']
            if auto_sync_enabled:
                log_message = f'API key regenerated for device {self.name} (ID: {self.id}) - Auto-sync failed, manual sync required'
                notification_message = _('New API key generated for %s. Auto-sync failed - please manually update the Virtual IoT Service and restart it.') % self.name
                notification_type = 'warning'
            else:
                log_message = f'API key regenerated for device {self.name} (ID: {self.id}) - Auto-sync disabled, manual sync required'
                notification_message = _('New API key generated for %s. Please manually update the Virtual IoT Service and restart it.') % self.name
                notification_type = 'info'
            
            security_util.log_security_event(
                'api_key_regenerated',
                log_message,
                device_id=self.id
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('API Key Regenerated'),
                    'message': notification_message,
                    'type': notification_type,
                }
            }
        else:
            # Auto-sync failed and fallback is disabled
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('API Key Regeneration Failed'),
                    'message': _('Failed to sync API key with device %s. Please check the connection and try again.') % self.name,
                    'type': 'danger',
                }
            }
    
    def _sync_api_key_with_service(self, old_key, new_key):
        """Sync the new API key with the Virtual IoT Service with retry logic"""
        # Get configuration parameters
        timeout = int(self.env['ir.config_parameter'].sudo().get_param(
            'virtual_iot.sync_timeout', '10'
        ))
        retry_attempts = int(self.env['ir.config_parameter'].sudo().get_param(
            'virtual_iot.sync_retry_attempts', '3'
        ))
        log_sync_events = self.env['ir.config_parameter'].sudo().get_param(
            'virtual_iot.log_sync_events', 'True'
        ).lower() == 'true'
        
        url = f"{self._get_base_url()}/admin/update-api-key"
        headers = {
            'Authorization': f'Bearer {old_key}',
            'Content-Type': 'application/json'
        }
        data = {
            'old_key': old_key,
            'new_key': new_key
        }
        
        last_error = None
        
        for attempt in range(retry_attempts):
            try:
                if log_sync_events and attempt > 0:
                    _logger.info(f"Retrying API key sync with Virtual IoT Service (attempt {attempt + 1}/{retry_attempts})")
                
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
                
                if response.status_code == 200:
                    result = response.json()
                    if log_sync_events:
                        _logger.info(f"Successfully synced API key with Virtual IoT Service: {result.get('message', 'Success')}")
                    return True
                elif response.status_code == 400:
                    # Bad request - don't retry
                    _logger.error(f"Bad request while syncing API key: {response.text}")
                    return False
                elif response.status_code == 401:
                    # Unauthorized - old key might be invalid, don't retry
                    _logger.error(f"Unauthorized while syncing API key - old key might be invalid")
                    return False
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    if log_sync_events:
                        _logger.warning(f"Failed to sync API key (attempt {attempt + 1}): {last_error}")
                    
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)}"
                if log_sync_events:
                    _logger.warning(f"Connection error during API key sync (attempt {attempt + 1}): {str(e)}")
                    
            except requests.exceptions.Timeout as e:
                last_error = f"Timeout error: {str(e)}"
                if log_sync_events:
                    _logger.warning(f"Timeout during API key sync (attempt {attempt + 1}): {str(e)}")
                    
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                _logger.error(f"Unexpected error during API key sync (attempt {attempt + 1}): {str(e)}")
                
            # Wait before retry (except for the last attempt)
            if attempt < retry_attempts - 1:
                import time
                time.sleep(1)  # Wait 1 second before retry
        
        # All attempts failed
        _logger.error(f"Failed to sync API key with Virtual IoT Service after {retry_attempts} attempts. Last error: {last_error}")
        return False

    @api.model
    def cron_check_device_status(self):
        """Cron job method to check status of all active devices and their printers"""
        devices = self.search([('active', '=', True)])
        _logger.info(f"Starting automatic status check for {len(devices)} devices")
        
        for device in devices:
            try:
                device.check_device_and_printer_status()
            except Exception as e:
                _logger.error(f"Error checking status for device {device.name}: {str(e)}")
        
        _logger.info("Automatic status check completed")

    def check_device_and_printer_status(self):
        """Check device connectivity and update printer statuses"""
        self.ensure_one()
        
        try:
            # First check if the device itself is reachable
            url = f"{self._get_base_url()}/health"
            response = requests.get(url, headers=self._get_headers(), timeout=5)
            
            if response.status_code == 200:
                # Device is online, update status and check printers
                self.write({
                    'status': 'online',
                    'last_seen': fields.Datetime.now()
                })
                
                # Check individual printer status
                self._check_printer_connectivity()
                
            else:
                # Device responded but with error
                self.write({'status': 'error'})
                # Mark all printers as offline
                self.printer_ids.write({'status': 'offline'})
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Device is not reachable
            self.write({'status': 'offline'})
            # Mark all printers as offline
            self.printer_ids.write({'status': 'offline'})
            
        except Exception as e:
            _logger.error(f"Unexpected error checking device {self.name}: {str(e)}")
            self.write({'status': 'error'})
            self.printer_ids.write({'status': 'offline'})

    def _check_printer_connectivity(self):
        """Check connectivity of individual printers"""
        self.ensure_one()
        
        try:
            # Get current printers from the Virtual IoT service
            url = f"{self._get_base_url()}/printers"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            
            if response.status_code == 200:
                printers_data = response.json()
                available_printer_names = {printer.get('name') for printer in printers_data}
                
                # Update printer statuses based on availability
                for printer in self.printer_ids:
                    if printer.name in available_printer_names:
                        # Printer is available, check if it was previously offline
                        if printer.status == 'offline':
                            printer.write({'status': 'ready'})
                    else:
                        # Printer is not available, mark as offline
                        if printer.status != 'offline':
                            printer.write({'status': 'offline'})
                            _logger.info(f"Printer {printer.name} marked as offline - not found in Virtual IoT service")
            else:
                _logger.warning(f"Failed to get printer list from device {self.name}: HTTP {response.status_code}")
                
        except Exception as e:
            _logger.error(f"Error checking printer connectivity for device {self.name}: {str(e)}")