# -*- coding: utf-8 -*-

import re
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class QWebProcessor(models.AbstractModel):
    """QWeb template processor for Virtual IoT printing"""
    _name = 'virtual.iot.qweb.processor'
    _description = 'QWeb Template Processor'

    def process_qweb_template(self, template_content, context_data):
        """
        Process QWeb template with context data
        
        Args:
            template_content (str): QWeb template content
            context_data (dict): Context data for template processing
            
        Returns:
            dict: {'success': bool, 'content': str, 'error': str}
        """
        try:
            if not template_content:
                return {'success': False, 'error': 'Template content is empty', 'content': ''}
            
            if not context_data:
                context_data = {}
            
            # Check if content is QWeb template
            if not self._is_qweb_template(template_content):
                # Return as-is if not QWeb
                return {'success': True, 'content': template_content, 'error': ''}
            
            # Process QWeb template
            processed_content = self._process_template(template_content, context_data)
            
            return {
                'success': True,
                'content': processed_content,
                'error': ''
            }
            
        except Exception as e:
            _logger.error(f"QWeb processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'content': template_content  # Return original on error
            }
    
    def _is_qweb_template(self, content):
        """Check if content contains QWeb directives"""
        qweb_patterns = [
            r't-esc=',
            r't-raw=',
            r't-if=',
            r't-foreach=',
            r't-as=',
            r't-value=',
            r't-field=',
            r't-att-',
            r't-set=',
            r't-call='
        ]
        
        for pattern in qweb_patterns:
            if re.search(pattern, content):
                return True
        return False
    
    def _process_template(self, template_content, context_data):
        """Process QWeb template with context data"""
        try:
            # Use Odoo's QWeb engine
            qweb = self.env['ir.qweb']
            
            # Create a temporary template
            template_name = f'virtual_iot_temp_{self.env.uid}_{fields.Datetime.now().timestamp()}'
            
            # Wrap template content in proper QWeb structure if needed
            if not template_content.strip().startswith('<?xml'):
                template_content = f'''<?xml version="1.0" encoding="utf-8"?>
<templates>
    <t t-name="{template_name}">
        {template_content}
    </t>
</templates>'''
            
            # Add template to QWeb
            qweb._compile_template(template_name, template_content)
            
            # Render template with context
            rendered_content = qweb._render(template_name, context_data)
            
            # Clean up temporary template
            if template_name in qweb._compiled_templates:
                del qweb._compiled_templates[template_name]
            
            return rendered_content
            
        except Exception as e:
            _logger.error(f"QWeb template processing failed: {str(e)}")
            # Fallback to simple variable replacement
            return self._simple_variable_replacement(template_content, context_data)
    
    def _simple_variable_replacement(self, content, context_data):
        """Simple fallback variable replacement for basic QWeb templates"""
        try:
            # Handle t-esc expressions
            def replace_t_esc(match):
                expr = match.group(1).strip()
                value = self._get_context_value(expr, context_data)
                return str(value) if value is not None else ''
            
            content = re.sub(r't-esc="([^"]*)"[^>]*>', replace_t_esc, content)
            
            # Handle t-if expressions
            def replace_t_if(match):
                condition = match.group(1).strip()
                element_content = match.group(2)
                
                if self._evaluate_condition(condition, context_data):
                    return element_content
                else:
                    return ''
            
            content = re.sub(r'<[^>]*t-if="([^"]*)"[^>]*>(.*?)</[^>]*>', replace_t_if, content, flags=re.DOTALL)
            
            # Handle t-foreach expressions
            def replace_t_foreach(match):
                collection_expr = match.group(1).strip()
                item_name = match.group(2).strip()
                element_content = match.group(3)
                
                collection = self._get_context_value(collection_expr, context_data)
                if not collection:
                    return ''
                
                result = ''
                for item in collection:
                    item_context = context_data.copy()
                    item_context[item_name] = item
                    item_content = self._simple_variable_replacement(element_content, item_context)
                    result += item_content
                
                return result
            
            content = re.sub(
                r'<[^>]*t-foreach="([^"]*)"[^>]*t-as="([^"]*)"[^>]*>(.*?)</[^>]*>',
                replace_t_foreach,
                content,
                flags=re.DOTALL
            )
            
            return content
            
        except Exception as e:
            _logger.error(f"Simple variable replacement failed: {str(e)}")
            return content
    
    def _get_context_value(self, expression, context_data):
        """Get value from context using dot notation"""
        try:
            keys = expression.split('.')
            value = context_data
            
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                elif hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return None
                
                if value is None:
                    return None
            
            return value
            
        except Exception:
            return None
    
    def _evaluate_condition(self, condition, context_data):
        """Evaluate simple conditions"""
        try:
            # Simple existence check
            if '.' in condition:
                value = self._get_context_value(condition, context_data)
                return bool(value)
            else:
                return bool(context_data.get(condition))
        except Exception:
            return False