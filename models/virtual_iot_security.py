"""
Security utilities for Virtual IoT Connector
"""

import hashlib
import hmac
import secrets
import time
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


class VirtualIoTSecurity(models.TransientModel):
    """Security utilities for Virtual IoT operations"""
    _name = 'virtual.iot.security'
    _description = 'Virtual IoT Security Utilities'

    @api.model
    def generate_api_key(self):
        """Generate a secure API key"""
        return secrets.token_urlsafe(32)

    @api.model
    def hash_api_key(self, api_key):
        """Hash an API key for secure storage"""
        salt = secrets.token_bytes(32)
        key_hash = hashlib.pbkdf2_hmac('sha256', api_key.encode(), salt, 100000)
        return salt.hex() + key_hash.hex()

    @api.model
    def verify_api_key(self, api_key, stored_hash):
        """Verify an API key against stored hash"""
        try:
            salt_hex = stored_hash[:64]  # First 32 bytes (64 hex chars)
            key_hash_hex = stored_hash[64:]  # Remaining bytes
            
            salt = bytes.fromhex(salt_hex)
            stored_key_hash = bytes.fromhex(key_hash_hex)
            
            new_key_hash = hashlib.pbkdf2_hmac('sha256', api_key.encode(), salt, 100000)
            return hmac.compare_digest(stored_key_hash, new_key_hash)
        except Exception:
            return False

    @api.model
    def create_signature(self, data, secret):
        """Create HMAC signature for data integrity"""
        return hmac.new(
            secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @api.model
    def verify_signature(self, data, signature, secret):
        """Verify HMAC signature"""
        expected_signature = self.create_signature(data, secret)
        return hmac.compare_digest(signature, expected_signature)

    @api.model
    def validate_ip_address(self, ip_address, allowed_ips=None):
        """Validate IP address against allowed list"""
        if not allowed_ips:
            return True
        
        # Support CIDR notation and wildcards
        import ipaddress
        try:
            ip = ipaddress.ip_address(ip_address)
            for allowed_ip in allowed_ips:
                if '/' in allowed_ip:
                    # CIDR notation
                    network = ipaddress.ip_network(allowed_ip, strict=False)
                    if ip in network:
                        return True
                elif '*' in allowed_ip:
                    # Wildcard notation (e.g., 192.168.1.*)
                    pattern = allowed_ip.replace('*', '.*')
                    import re
                    if re.match(pattern, ip_address):
                        return True
                elif ip_address == allowed_ip:
                    return True
            return False
        except Exception:
            return False

    @api.model
    def log_security_event(self, event_type, details, user_id=None, ip_address=None, device_id=None, printer_id=None):
        """Log security events for auditing"""
        log_data = {
            'event_type': event_type,
            'details': details,
            'user_id': user_id or self.env.user.id,
            'ip_address': ip_address,
            'timestamp': fields.Datetime.now(),
        }
        
        # Add device_id if provided
        if device_id:
            log_data['device_id'] = device_id
            
        # Add printer_id if provided
        if printer_id:
            log_data['printer_id'] = printer_id
            
        self.env['virtual.iot.security.log'].create(log_data)


class VirtualIoTSecurityLog(models.Model):
    """Security event logging"""
    _name = 'virtual.iot.security.log'
    _description = 'Virtual IoT Security Log'
    _order = 'timestamp desc'
    _rec_name = 'event_type'

    event_type = fields.Selection([
        ('api_key_generated', 'API Key Generated'),
        ('api_key_regenerated', 'API Key Regenerated'),
        ('device_registered', 'Device Registered'),
        ('device_connection_test', 'Device Connection Test'),
        ('unauthorized_access', 'Unauthorized Access Attempt'),
        ('print_job_submitted', 'Print Job Submitted'),
        ('print_job_failed', 'Print Job Failed'),
        ('configuration_changed', 'Configuration Changed'),
    ], string='Event Type', required=True)
    
    details = fields.Text('Details')
    user_id = fields.Many2one('res.users', string='User', required=True)
    ip_address = fields.Char('IP Address')
    timestamp = fields.Datetime('Timestamp', required=True, default=fields.Datetime.now)
    
    # Related fields for easier filtering
    device_id = fields.Many2one('virtual.iot.device', string='Device')
    printer_id = fields.Many2one('virtual.iot.printer', string='Printer')

    @api.model
    def cleanup_old_logs(self, days=30):
        """Clean up old security logs"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('timestamp', '<', cutoff_date)])
        old_logs.unlink()
        return len(old_logs)


class VirtualIoTAccessControl(models.Model):
    """Access control for Virtual IoT operations"""
    _name = 'virtual.iot.access.control'
    _description = 'Virtual IoT Access Control'

    name = fields.Char('Rule Name', required=True)
    active = fields.Boolean('Active', default=True)
    
    # Access control settings
    allowed_users = fields.Many2many('res.users', string='Allowed Users')
    allowed_groups = fields.Many2many('res.groups', string='Allowed Groups')
    allowed_ip_addresses = fields.Text('Allowed IP Addresses', 
                                      help='One per line. Supports CIDR notation and wildcards.')
    
    # Time-based restrictions
    time_restricted = fields.Boolean('Time Restricted')
    allowed_hours_start = fields.Float('Start Hour', default=0.0)
    allowed_hours_end = fields.Float('End Hour', default=24.0)
    allowed_days = fields.Selection([
        ('weekdays', 'Weekdays Only'),
        ('weekends', 'Weekends Only'),
        ('all', 'All Days'),
    ], string='Allowed Days', default='all')
    
    # Operation restrictions
    operations = fields.Selection([
        ('all', 'All Operations'),
        ('read_only', 'Read Only'),
        ('print_only', 'Print Only'),
        ('admin_only', 'Admin Only'),
    ], string='Allowed Operations', default='all')

    @api.model
    def check_access(self, user_id, operation, ip_address=None):
        """Check if user has access for the operation"""
        user = self.env['res.users'].browse(user_id)
        
        # Get active access control rules
        rules = self.search([('active', '=', True)])
        
        if not rules:
            # No rules defined, allow access
            return True
        
        for rule in rules:
            if self._check_rule_access(rule, user, operation, ip_address):
                return True
        
        return False

    def _check_rule_access(self, rule, user, operation, ip_address):
        """Check access against a specific rule"""
        # Check user/group access
        if rule.allowed_users and user not in rule.allowed_users:
            if not any(group in user.groups_id for group in rule.allowed_groups):
                return False
        
        # Check IP address
        if ip_address and rule.allowed_ip_addresses:
            allowed_ips = [ip.strip() for ip in rule.allowed_ip_addresses.split('\n') if ip.strip()]
            security_util = self.env['virtual.iot.security']
            if not security_util.validate_ip_address(ip_address, allowed_ips):
                return False
        
        # Check time restrictions
        if rule.time_restricted:
            from datetime import datetime
            now = datetime.now()
            current_hour = now.hour + now.minute / 60.0
            
            if not (rule.allowed_hours_start <= current_hour <= rule.allowed_hours_end):
                return False
            
            if rule.allowed_days == 'weekdays' and now.weekday() >= 5:
                return False
            elif rule.allowed_days == 'weekends' and now.weekday() < 5:
                return False
        
        # Check operation restrictions
        if rule.operations == 'read_only' and operation not in ['read', 'list']:
            return False
        elif rule.operations == 'print_only' and operation not in ['read', 'list', 'print']:
            return False
        elif rule.operations == 'admin_only' and not user.has_group('virtual_iot_connector.group_virtual_iot_manager'):
            return False
        
        return True