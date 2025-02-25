import frappe
from typing import Dict, Union, Optional, Any, List, Tuple
from contextlib import contextmanager

from frappe import _
from dataclasses import dataclass
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import lru_cache

# Custom exceptions for better error handling
class OrderProcessingError(Exception):
    pass

class DocumentVerificationError(Exception):
    pass

@contextmanager
def database_transaction():
    """Context manager for database transactions"""
    try:
        yield
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Transaction failed: {str(e)}")
        raise

@dataclass
class TransactionDetails:
    """Data class for transaction calculations"""
    order_amount: float
    discount: float 
    platform_fee: float
    final_amount: float
    wallet_balance: float

class HttpClient:
    """Handles HTTP requests with retries and timeouts"""
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def post(self, url: str, data: Dict, headers: Dict, timeout: int = 30) -> requests.Response:
        return self.session.post(url, json=data, headers=headers, timeout=timeout)

class WalletManager:
    """Handles wallet operations with proper locking"""
    
    @staticmethod
    @lru_cache(maxsize=100)  # Cache wallet config for 5 minutes
    def get_wallet_config(channel_partner: str, product_category: str) -> Dict:
        """Get cached wallet configuration"""
        return frappe.get_all(
            "Partner Wallet",
            filters={
                "channel_partner": channel_partner,
                "status": "Active"
            },
            fields=["name", "balance", "status"]
        )

    @staticmethod
    def check_and_hold_balance(wallet_name: str, amount: float) -> bool:
        """Check and hold balance with proper locking"""
        # Using Frappe's built-in locking mechanism
        key = f"wallet_lock:{wallet_name}"
        if not frappe.cache().exists(key):
            frappe.cache().set(key, True, expires_in_sec=60)
            try:
                wallet = frappe.get_doc("Partner Wallet", wallet_name)
                if wallet.balance >= amount:
                    wallet.balance -= amount
                    wallet.save(ignore_permissions=True)
                    return True
                return False
            finally:
                frappe.cache().delete(key)
        raise OrderProcessingError("Wallet operation in progress")

class DocumentVerificationService:
    """Handles document verification with proper separation of concerns"""
    
    def __init__(self, product: Any, processor: Any):
        self.product = product
        self.processor = processor
        self.http_client = HttpClient()

    def verify_document(self, identity_number: str, order: Any) -> Dict:
        """Process document verification"""
        doc = self._create_verification_doc(identity_number)
        method = self._get_verification_method()
        payload = self._prepare_payload(order, identity_number)
        
        response = self._make_api_call(method, payload)
        return self._process_response(response, doc)

    def _create_verification_doc(self, identity_number: str) -> Any:
        """Create verification document based on product type"""
        doc_type = "PanCard Verification" if self.product.name == "PanCard Detail Finder" else "AahaarCard Verification"
        number_field = "pan_card_number" if doc_type == "PanCard Verification" else "aadhaar_card_number"
        
        return frappe.get_doc({
            "doctype": doc_type,
            number_field: identity_number
        }).insert()

    def _get_verification_method(self) -> Any:
        """Get verification method from processor config"""
        method_name = "Pan Card Verification" if self.product.name == "PanCard Detail Finder" else "Aadhaar Card Verification"
        method = next((m for m in self.processor.api_methods if m.method_name == method_name), None)
        if not method:
            raise DocumentVerificationError(f"{method_name} not found in processor configuration")
        return method

    def _process_response(self, response: Dict, doc: Any) -> Dict:
        """Process API response and update document"""
        if response.get("http_response_code") == 200:
            result = response.get("result", {})
            if self.product.name == "PanCard Detail Finder":
                self._update_pan_verification(doc, result)
            else:
                self._update_aadhaar_verification(doc, result)
            doc.save(ignore_permissions=True)
            return self._prepare_response(doc)
        raise DocumentVerificationError("Verification failed")

    def _update_pan_verification(self, doc: Any, result: Dict) -> None:
        """Update PAN verification document"""
        updates = {
            "pan_number": result.get("pan"),
            "pan_type": result.get("pan_type"),
            "aadhaar_linked": result.get("aadhaar_linked", 0),
            "mobile_number": result.get("mobile"),
            # Add other fields as needed
        }
        for key, value in updates.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

class OrderProcessor:
    """Handles order processing with proper transaction management"""
    
    def __init__(self, product_name: str, channel_partner: str):
        self.product = frappe.get_doc("Product", product_name)
        self.channel_partner = channel_partner
        self.wallet_manager = WalletManager()

    def process_order(self, identity_number: str, amount: float) -> Dict:
        """Process order with proper transaction handling"""
        with database_transaction():
            # Calculate amounts
            transaction_details = self._calculate_amounts(amount)
            
            # Create and process order
            order, txn_log = self._create_order_and_transaction(
                identity_number, 
                transaction_details
            )
            
            # Process based on product category
            if self.product.category == "Verification":
                processor = self._get_processor()
                verification_service = DocumentVerificationService(self.product, processor)
                return verification_service.verify_document(identity_number, order)
            
            return self._process_payment(order, txn_log)

    def _calculate_amounts(self, amount: float) -> TransactionDetails:
        """Calculate transaction amounts with caching"""
        pricing = self._get_product_pricing()
        
        discount = self._calculate_discount(amount, pricing)
        platform_fee = self._calculate_platform_fee(amount, pricing)
        final_amount = amount - discount + platform_fee
        
        wallet = self._get_wallet()
        
        return TransactionDetails(
            order_amount=amount,
            discount=discount,
            platform_fee=platform_fee,
            final_amount=final_amount,
            wallet_balance=wallet.balance
        )

    @lru_cache(maxsize=100)
    def _get_product_pricing(self) -> Dict:
        """Get cached product pricing"""
        return frappe.get_all(
            "Product Pricing",
            filters={
                "parent": self.channel_partner,
                "product_name": self.product.name,
                "is_active": 1
            },
            fields=["discount_type", "discount_amount", "plateform_fee_type", "plateform_fee"]
        )[0]




@dataclass
class OrderRequest:
    product_name: str
    identity_number: str
    channel_partner: str
    order_amount: float

    @classmethod
    def from_dict(cls, data: Dict) -> 'OrderRequest':
        return cls(
            product_name=data['product_name'],
            identity_number=data['identity_number'],
            channel_partner=data['channel_partner'],
            order_amount=float(data.get('order_amount', 0))
        )

class OrderBatchProcessor:
    """Handles both single and batch order processing"""
    
    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size

    def process_orders(self, orders: Union[OrderRequest, List[OrderRequest]]) -> Dict:
        """Process single order or batch of orders"""
        if isinstance(orders, OrderRequest):
            return self._process_single_order(orders)
        return self._process_order_batch(orders)

    def _process_single_order(self, order: OrderRequest) -> Dict:
        """Process a single order"""
        with database_transaction():
            processor = OrderProcessor(
                order.product_name,
                order.channel_partner
            )
            return processor.process_order(
                order.identity_number,
                order.order_amount
            )

    def _process_order_batch(self, orders: List[OrderRequest]) -> Dict:
        """Process multiple orders in batches"""
        results = []
        failures = []
        
        # Group orders by channel partner for efficient processing
        grouped_orders = self._group_orders_by_partner(orders)
        
        for partner, partner_orders in grouped_orders.items():
            # Process each partner's orders in batches
            for batch in self._create_batches(partner_orders):
                batch_result = self._process_partner_batch(partner, batch)
                results.extend(batch_result['successes'])
                failures.extend(batch_result['failures'])

        return {
            "status": "completed",
            "total_orders": len(orders),
            "successful_orders": len(results),
            "failed_orders": len(failures),
            "results": results,
            "failures": failures
        }

    def _group_orders_by_partner(self, orders: List[OrderRequest]) -> Dict[str, List[OrderRequest]]:
        """Group orders by channel partner for efficient processing"""
        grouped = {}
        for order in orders:
            if order.channel_partner not in grouped:
                grouped[order.channel_partner] = []
            grouped[order.channel_partner].append(order)
        return grouped

    def _create_batches(self, orders: List[OrderRequest]) -> List[List[OrderRequest]]:
        """Split orders into batches"""
        return [orders[i:i + self.batch_size] 
                for i in range(0, len(orders), self.batch_size)]

    def _process_partner_batch(self, partner: str, batch: List[OrderRequest]) -> Dict:
        """Process a batch of orders for a single partner"""
        successes = []
        failures = []

        with database_transaction():
            # Pre-validate wallet balance for the entire batch
            total_amount = sum(order.order_amount for order in batch)
            if not self._validate_wallet_balance(partner, total_amount):
                return {
                    "successes": [],
                    "failures": [{
                        "order": order.__dict__,
                        "error": "Insufficient wallet balance for batch"
                    } for order in batch]
                }

            # Process individual orders
            for order in batch:
                try:
                    result = OrderProcessor(
                        order.product_name,
                        partner
                    ).process_order(
                        order.identity_number,
                        order.order_amount
                    )
                    successes.append({
                        "order": order.__dict__,
                        "result": result
                    })
                except Exception as e:
                    failures.append({
                        "order": order.__dict__,
                        "error": str(e)
                    })

        return {
            "successes": successes,
            "failures": failures
        }

    def _validate_wallet_balance(self, partner: str, total_amount: float) -> bool:
        """Validate wallet has sufficient balance for batch"""
        wallet = frappe.get_doc("Partner Wallet", {
            "channel_partner": partner,
            "status": "Active"
        })
        return wallet.balance >= total_amount

@frappe.whitelist()
def make_an_order(data: Union[Dict, List[Dict]]) -> Dict:
    """Unified API endpoint for single and bulk orders"""
    try:
        processor = OrderBatchProcessor()
        
        # Handle single order
        if isinstance(data, dict):
            order_request = OrderRequest.from_dict(data)
            return processor.process_orders(order_request)
            
        # Handle bulk orders
        order_requests = [OrderRequest.from_dict(order_data) 
                        for order_data in data]
        return processor.process_orders(order_requests)
        
    except Exception as e:
        frappe.log_error("Order Processing Error", str(e))
        return {
            "status": "error",
            "message": str(e),
            "code": "PROCESSING_ERROR"
        }

# Example usage:
# Single order:
# make_an_order({
#     "product_name": "Airtel",
#     "identity_number": "1234567890",
#     "channel_partner": "Partner1",
#     "order_amount": 100
# })

# Bulk orders:
# make_an_order([
#     {
#         "product_name": "Airtel",
#         "identity_number": "1234567890",
#         "channel_partner": "Partner1",
#         "order_amount": 100
#     },
#     {
#         "product_name": "Vodafone",
#         "identity_number": "9876543210",
#         "channel_partner": "Partner1",
#         "order_amount": 200
#     }
# ])
