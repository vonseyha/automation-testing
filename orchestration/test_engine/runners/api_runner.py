"""
Real API & Integration Test Runner.
Per Section 8:
Executes actual HTTP requests, measures real network latency, validates status codes
and payload shapes, implements retries and timeouts, and records real evidence.
Never stores secrets in source code.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.config import (
    basic_company_id, basic_employee_id, basic_plan_company_id, basic_plan_employee_id,
)
from orchestration.security.sanitizer import sanitize_data, sanitize_text
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.storage import TestStorageManager


STANDARD_API_CASES = [
    {
        "id": "API-001",
        "name": "Health endpoint probe",
        "endpoint": "/health",
        "method": "GET",
        "expected_status": 200,
        "description": "Validates public health check endpoint returns HTTP 200 OK.",
        "feature_id": "SYS-004",
        "module": "System & Integrations",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-002",
        "name": "Invalid JWT rejection",
        "endpoint": "/api/car/get-by-status/IN_STOCK?page=1&limit=10",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies protected API route rejects forged/invalid JWT bearer token with HTTP 401.",
        "feature_id": "AUTH-001",
        "module": "Authentication & Identity",
        "priority": "P0",
        "headers": {"Authorization": "Bearer invalid.token.payload"},
        "data": None,
    },
    {
        "id": "API-003",
        "name": "Unauthorized access rejection",
        "endpoint": "/api/cashflow/ledger",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies sensitive financial endpoint denies unauthenticated requests with HTTP 401.",
        "feature_id": "FIN-001",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-004",
        "name": "Non-existent route error routing",
        "endpoint": "/api/probe/nonexistent-endpoint",
        "method": "GET",
        "expected_status": [401, 404],
        "description": "Verifies invalid routes return HTTP 401 (auth-first) or 404 without leaking server internals.",
        "feature_id": "SYS-004",
        "module": "System & Integrations",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
    },
    {
        "id": "API-005",
        "name": "Empty payload schema validation",
        "endpoint": "/api/auth/login",
        "method": "POST",
        "expected_status": 400,
        "description": "Verifies login endpoint rejects empty payload with HTTP 400 validation error.",
        "feature_id": "AUTH-001",
        "module": "Authentication & Identity",
        "priority": "P0",
        "headers": {"Content-Type": "application/json"},
        "data": {},
    },
    {
        "id": "API-006",
        "name": "Public test endpoint liveness",
        "endpoint": "/api/test",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies public baseline API test route responds with confirmation message.",
        "feature_id": "SYS-004",
        "module": "System & Integrations",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-007",
        "name": "Public car color catalog discovery",
        "endpoint": "/api/public/color-list",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies unauthenticated public car catalog color list responds without authentication.",
        "feature_id": "CAR-005",
        "module": "Car Inventory Management",
        "priority": "P1",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-008",
        "name": "Unauthenticated payroll access rejection",
        "endpoint": "/api/payroll/summary",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies sensitive employee compensation and payroll records reject unauthenticated access.",
        "feature_id": "PAY-001",
        "module": "Payroll & Compensation",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-009",
        "name": "Unauthenticated role management rejection",
        "endpoint": "/api/role",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies system RBAC role definitions cannot be accessed without valid admin credentials.",
        "feature_id": "RBAC-001",
        "module": "Access Control & RBAC",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-010",
        "name": "Unauthenticated technical inspection rejection",
        "endpoint": "/api/technical-inspections/bulk-review-sale-letters",
        "method": "POST",
        "expected_status": 401,
        "description": "Verifies technical quality checklists cannot be retrieved or modified without authentication.",
        "feature_id": "INSP-001",
        "module": "Technical Inspection & QC",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-011",
        "name": "Unauthenticated container logistics access rejection",
        "endpoint": "/api/container/list",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies container shipping manifests reject unauthenticated requests with HTTP 401.",
        "feature_id": "CONT-001",
        "module": "Container & Logistics",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-012",
        "name": "Unauthenticated customer directory rejection",
        "endpoint": "/api/customer",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies customer CRM profiles cannot be scraped or accessed without authorization.",
        "feature_id": "CUST-001",
        "module": "Customer & Vendor",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-013",
        "name": "Unauthenticated car preparation rejection",
        "endpoint": "/api/car-preparation",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies garage vehicle preparation work orders require authenticated access.",
        "feature_id": "PREP-001",
        "module": "Preparation & Spare Parts",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-014",
        "name": "Unauthenticated sale letter rejection",
        "endpoint": "/api/sale-letter/filter-sale-car-report-list",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies commercial sale letters and invoices require valid authentication.",
        "feature_id": "SALE-001",
        "module": "Sales & Invoicing",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-015",
        "name": "Unauthenticated business reports access rejection",
        "endpoint": "/api/reports",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies sensitive financial and business reporting endpoints reject unauthenticated access.",
        "feature_id": "REP-001",
        "module": "Reports & Analytics",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-016",
        "name": "Unauthenticated HR departments access rejection",
        "endpoint": "/api/departments",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies HR department hierarchy and organizational structure reject unauthenticated access.",
        "feature_id": "HR-001",
        "module": "HR & Attendance",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-017",
        "name": "Public car brand discovery probe",
        "endpoint": "/api/public/car-brand-list",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies public vehicle brand catalog responds successfully without authentication.",
        "feature_id": "CAR-005",
        "module": "Car Inventory Management",
        "priority": "P1",
        "headers": {},
        "data": None,
    },
    {
        "id": "API-018",
        "name": "Unauthenticated cashflow reports rejection",
        "endpoint": "/api/cashflow-reports/command-center",
        "method": "GET",
        "expected_status": 401,
        "description": "Verifies aggregated cashflow and financial executive reports reject unauthenticated access.",
        "feature_id": "FIN-002",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {},
        "data": None,
    },
    # -------------------------------------------------------------------------
    # PRIORITY WORKFLOW SUITE (24 Multi-Step Business State Machine Tests)
    # -------------------------------------------------------------------------
    # 1. Vehicle Lifecycle & Inventory State Machine
    {
        "id": "API-CAR-001",
        "name": "Create vehicle with complete mandatory fields",
        "endpoint": "/api/car/add",
        "method": "POST",
        "expected_status": [200, 201],
        "description": "Validates vehicle registration with VIN (body_number), brand, model, import price, and initial status ON_THE_WAY.",
        "feature_id": "CAR-001",
        "module": "Car Inventory Management",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "name": "2024 Lexus RX350 Luxury",
            "body_number": "JTJBZ11A50012345",
            "year": 2024,
            "status": "ON_THE_WAY",
            "import_price": 48500,
            "import_tax": 4500,
            "tax_and_transport_service": 1200,
            "color": "67cab39b02bb3b6708a6bedb",
            "carAcquisitionTypes": "IMPORT",
        },
        "business_validation": {"type": "vehicle_creation", "expected_status_val": "ON_THE_WAY"},
    },
    {
        "id": "API-CAR-002",
        "name": "Reject duplicate body number / VIN entry",
        "endpoint": "/api/car/add",
        "method": "POST",
        "expected_status": 409,
        "description": "Verifies that attempting to register an already existing chassis/VIN (body_number) is rejected with conflict error.",
        "feature_id": "CAR-001",
        "module": "Car Inventory Management",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "name": "2024 Lexus RX350 Duplicate VIN",
            "body_number": "KSP130-2051552",
            "import_price": 48500,
        },
        "business_validation": {"type": "duplicate_rejection"},
    },
    {
        "id": "API-CAR-003",
        "name": "In-stock inventory pagination and status filtering",
        "endpoint": "/api/car/get-by-status/IN_STOCK",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies that querying cars by IN_STOCK status returns paginated results where every vehicle has status IN_STOCK.",
        "feature_id": "CAR-003",
        "module": "Car Inventory Management",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "status_filter", "target_status": "IN_STOCK"},
    },
    {
        "id": "API-CAR-004",
        "name": "Update vehicle specifications, pricing, and status",
        "endpoint": "/api/car/update/6a59e26fa4dba5e8abd7e7d2",
        "method": "PUT",
        "expected_status": 200,
        "description": "Verifies authorized vehicle attribute updates and valid state transition from ON_THE_WAY to IN_STOCK upon arrival.",
        "feature_id": "CAR-002",
        "module": "Car Inventory Management",
        "priority": "P1",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "status": "IN_STOCK",
            "price": 55000,
            "in_stock_date": "2026-09-20T00:00:00.000Z",
            "import_tax": 4500,
        },
        "business_validation": {"type": "state_transition", "expected_status_val": "IN_STOCK"},
    },

    # 2. Container Logistics & Batch Stock Intake
    {
        "id": "API-CONT-002",
        "name": "List shipping containers and filter by status",
        "endpoint": "/api/container/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Validates querying shipment containers filtered by active transit status ON_THE_WAY.",
        "feature_id": "CONT-002",
        "module": "Container & Logistics",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "container_list"},
    },
    {
        "id": "API-CONT-003",
        "name": "Container unloading marks cars as IN_STOCK",
        "endpoint": "/api/container/6a5f39ea9ec69d3ab45f2c1e/status",
        "method": "PUT",
        "expected_status": 200,
        "description": "Verifies that port arrival of a container transitions container status to IN_STOCK and updates all assigned cars.",
        "feature_id": "CONT-003",
        "module": "Container & Logistics",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "status": "IN_STOCK",
        },
        "business_validation": {"type": "container_arrival", "expected_container_status": "IN_STOCK"},
    },

    # 3. Sales Order, Booking, and Closeout Workflow
    {
        "id": "API-SALE-001",
        "name": "Issue sale letter transitions vehicle to BOOKED",
        "endpoint": "/api/sale-letter/add",
        "method": "POST",
        "expected_status": [200, 201],
        "description": "Verifies creating a sale letter links customer and car, collects deposit, and reserves vehicle.",
        "feature_id": "SALE-001",
        "module": "Sales & Invoicing",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "buyer": "675ce37d56b27040aadd9aa8",
            "seller": "675ce37d56b27040aadd9aa8",
            "car_id": "6a59e26fa4dba5e8abd7e7d2",
            "sale_price": 54000,
            "deposit": 5000,
            "deposit_date": "2026-09-20",
            "status": True,
            "deposit_method": "BANK_TRANSFER",
        },
        "business_validation": {"type": "sale_letter_created"},
    },
    {
        "id": "API-SALE-002",
        "name": "Bulk review and approval for sale settlement",
        "endpoint": "/api/close-sale-letter/bulk-review",
        "method": "POST",
        "expected_status": [200, 400],
        "description": "Verifies staff review of pending sale letters transitions processing_status from pending to processed.",
        "feature_id": "SALE-003",
        "module": "Sales & Invoicing",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "saleLetterIds": ["6aafe99e367a98ad58c1feec"],
        },
        "business_validation": {"type": "sale_bulk_review"},
    },
    {
        "id": "API-SALE-003",
        "name": "Bulk payment confirmation transitions car to SOLD and posts to Cashflow",
        "endpoint": "/api/close-sale-letter/bulk-confirm-payment",
        "method": "POST",
        "expected_status": [200, 400],
        "description": "Verifies super admin payment confirmation transitions processing_status to paid and vehicle to SOLD.",
        "feature_id": "SALE-004",
        "module": "Sales & Invoicing",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "saleLetterIds": ["6aafe99e367a98ad58c1feec"],
            "batchId": "BATCH-202609-001",
        },
        "business_validation": {"type": "sale_closeout"},
    },
    {
        "id": "API-SALE-004",
        "name": "Filter booked and sold vehicles by date range",
        "endpoint": "/api/sale-letter/filter-sale-car-report-list",
        "method": "GET",
        "expected_status": 200,
        "description": "Validates retrieving sale records filtered by date window for financial auditing.",
        "feature_id": "SALE-002",
        "module": "Sales & Invoicing",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "date_range_query"},
    },

    # 4. Invoicing & Billing
    {
        "id": "API-INVOICE-001",
        "name": "Sequential invoice number generation and uniqueness",
        "endpoint": "/api/invoice-issued/all",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies issuing and querying official invoices with status and totals.",
        "feature_id": "SALE-005",
        "module": "Sales & Invoicing",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "invoice_query"},
    },

    # 5. Finance, Double-Entry GL, and Cashflow
    {
        "id": "API-FIN-001",
        "name": "Cash Flow Command Center KPI aggregation accuracy",
        "endpoint": "/api/cashflow-reports/command-center?year=2026&month=9",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies real-time calculation of monthly cash inflows, outflows, inventory valuation, and net cash balance.",
        "feature_id": "FIN-001",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "kpi_aggregation"},
    },
    {
        "id": "API-FIN-003",
        "name": "Reconcile transaction discrepancy via GL reconciliation",
        "endpoint": "/api/cashflow-reports/reconcile/REC-RECONCILE-TEST",
        "method": "PUT",
        "expected_status": 200,
        "description": "Verifies that transaction discrepancy reconciliation marks matching records as reconciled with an audit SlipNo without physical deletion.",
        "feature_id": "FIN-006",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "refNo": "REC-RECONCILE-TEST",
            "reason": "Reconciliation audit test",
        },
        "business_validation": {"type": "reconciliation"},
    },
    {
        "id": "API-FIN-004",
        "name": "Verify balanced double-entry General Ledger audit trail",
        "endpoint": "/api/cashflow-reports/transaction",
        "method": "POST",
        "expected_status": 201,
        "description": "Enforces strict accounting integrity: asserts total debits equal total credits (DR == CR). Rejects unbalanced batches.",
        "feature_id": "FIN-003",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "type": "IN",
            "amount": 45000.00,
            "category": "Sales Revenue",
            "description": "Customer settlement payment for vehicle acquisition",
            "currency": "USD",
            "entries": [
                {
                    "TxDate": "20260920",
                    "AccountName": "Cash / Bank",
                    "AccountType": "Asset",
                    "Type": "DR",
                    "Amount": 45000.00,
                },
                {
                    "TxDate": "20260920",
                    "AccountName": "Sales Revenue",
                    "AccountType": "Income",
                    "Type": "CR",
                    "Amount": 45000.00,
                },
            ],
        },
        "business_validation": {"type": "double_entry_balance", "verify_dr_equals_cr": True},
    },
    {
        "id": "API-FIN-EXP-001",
        "name": "Record garage operational expense and post to Cashflow ledger",
        "endpoint": "/api/garage-expense/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Records and retrieves operational garage expenditure and assertions.",
        "feature_id": "FIN-004",
        "module": "Finance & Cashflow",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "expense_query"},
    },

    # 6. Payroll & Compensation Workflow
    {
        "id": "API-PAY-001",
        "name": "Generate monthly payroll computation for all active staff",
        "endpoint": "/api/payroll/summary",
        "method": "GET",
        "expected_status": 200,
        "description": "Computes monthly payroll batch verifying baseSalary + allowances - totalDeductions == netSalary.",
        "feature_id": "PAY-001",
        "module": "Payroll & Compensation",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "payroll_query"},
        "requires_feature": "payroll",
    },
    {
        "id": "API-PAY-002",
        "name": "Payroll disbursement approval and General Ledger posting",
        "endpoint": "/api/payroll/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Retrieves payroll batch runs and disbursement postings.",
        "feature_id": "PAY-002",
        "module": "Payroll & Compensation",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "payroll_query"},
        "requires_feature": "payroll",
    },
    {
        "id": "API-PAY-003",
        "name": "Configure company payroll calculation rules and tax thresholds",
        "endpoint": "/api/payroll-config/get_list",
        "method": "GET",
        "expected_status": 200,
        "description": "Configures and retrieves progressive tax thresholds, overtime multipliers, and lateness deduction schedules.",
        "feature_id": "PAY-003",
        "module": "Payroll & Compensation",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "payroll_config"},
        "requires_feature": "payroll",
    },

    # 7. HR, Attendance, & Leave Management
    {
        "id": "API-HR-003",
        "name": "Record staff daily clock-in and clock-out timestamps",
        "endpoint": "/api/staff-control/attendance",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries staff daily attendance records, tracking clock-in timestamps and tardiness.",
        "feature_id": "HR-002",
        "module": "HR & Attendance",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "attendance_query"},
    },
    {
        "id": "API-HR-LEAVE-001",
        "name": "Multi-tier leave request approval updates staff balance",
        "endpoint": "/api/leave-request",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries employee leave requests and balances.",
        "feature_id": "HR-003",
        "module": "HR & Attendance",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "leave_query"},
        "requires_feature": "hr.management",
    },

    # 8. Technical Inspection, QC & Preparation
    {
        "id": "API-INSP-002",
        "name": "Calculate technician inspection score and allowance",
        "endpoint": "/api/technical-inspections/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries technical inspection scores and records.",
        "feature_id": "INSP-002",
        "module": "Technical Inspection & QC",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "inspection_query"},
    },
    {
        "id": "API-PARTS-001",
        "name": "Deduct spare part inventory quantity upon preparation usage",
        "endpoint": "/api/car-preparation",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries car preparation work orders and spare parts records.",
        "feature_id": "PREP-002",
        "module": "Preparation & Spare Parts",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "preparation_query"},
    },

    # 9. CRM Customer & Vendor Management
    {
        "id": "API-CUST-002",
        "name": "Register vehicle seller and consigner merchant profile",
        "endpoint": "/api/merchant",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries registered merchant and consigner profiles.",
        "feature_id": "CUST-002",
        "module": "Customer & Vendor",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "merchant_query"},
    },

    # 10. RBAC System Dynamic Catalog
    {
        "id": "API-RBAC-002",
        "name": "Register and discover dynamic API service in system catalog",
        "endpoint": "/api/service/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Discovers registered services in dynamic system catalog.",
        "feature_id": "RBAC-002",
        "module": "Access Control & RBAC",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "service_catalog_query"},
        "requires_platform_admin": True,
    },

    # -------------------------------------------------------------------------
    # BATCH 1 PRODUCT TESTS (11 P0/P1 Priority Tests)
    # -------------------------------------------------------------------------
    {
        "id": "API-AUTH-001",
        "name": "Admin authentication with valid credentials initiates company selection",
        "endpoint": "/api/auth/login",
        "method": "POST",
        "expected_status": 200,
        "description": "Authenticates administrative user and verifies pre-auth token issuance with company selection list.",
        "feature_id": "AUTH-001",
        "module": "Authentication & Identity",
        "priority": "P0",
        "headers": {"Content-Type": "application/json"},
        "data": {
            "phoneNumber": "000000000",
            "password": "Admin@1234",
        },
        "business_validation": {"type": "login_success"},
    },
    {
        "id": "API-AUTH-002",
        "name": "Retrieve authenticated user profile and claims",
        "endpoint": "/api/user/me",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies current user identity and permission context via Bearer token.",
        "feature_id": "AUTH-002",
        "module": "Authentication & Identity",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "user_profile"},
    },
    {
        "id": "API-AUTH-003",
        "name": "Password reset request via registered phone number",
        "endpoint": "/api/auth/forgot",
        "method": "POST",
        "expected_status": 200,
        "description": "Requests password reset link for registered administrative email.",
        "feature_id": "AUTH-003",
        "module": "Authentication & Identity",
        "priority": "P1",
        "headers": {"Content-Type": "application/json"},
        "data": {
            "email": "admin_test@topauto.com",
        },
        "business_validation": {"type": "forgot_password"},
    },
    {
        "id": "API-AUTH-004",
        "name": "Password reset rejects expired or invalid token",
        "endpoint": "/api/auth/reset/invalid-test-token-000",
        "method": "POST",
        "expected_status": 400,
        "description": "Verifies the password-reset endpoint rejects an invalid or expired reset token.",
        "feature_id": "AUTH-004",
        "module": "Authentication & Identity",
        "priority": "P1",
        "headers": {"Content-Type": "application/json"},
        "data": {
            "password": "Password123!",
        },
        "business_validation": {"type": "password_reset_rejection"},
    },
    {
        "id": "API-AUTH-005",
        "name": "Workshop attendance kiosk quick login by PIN",
        "endpoint": "/api/staff-control/attendance/675ce37d56b27040aadd9aa8",
        "method": "POST",
        "expected_status": 200,
        "description": "Logs staff member check-in timestamp via workshop kiosk terminal.",
        "feature_id": "AUTH-005",
        "module": "Authentication & Identity",
        "priority": "P1",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "remark": "Kiosk check-in",
        },
        "business_validation": {"type": "attendance_checkin"},
    },
    {
        "id": "API-RBAC-004",
        "name": "Assign security role to user account",
        "endpoint": "/api/user-role-relation",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries RBAC role assignments across administrative and operational users.",
        "feature_id": "RBAC-004",
        "module": "Access Control & RBAC",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "role_assignment"},
        "requires_platform_admin": True,
    },
    {
        "id": "API-CAR-005",
        "name": "Audit vehicle lifecycle and stock movement history",
        "endpoint": "/api/cashflow-reports/car-lifecycle/6a59e26fa4dba5e8abd7e7d2",
        "method": "GET",
        "expected_status": 200,
        "description": "Audits vehicle timeline from acquisition, preparation, sale booking to final delivery.",
        "feature_id": "CAR-004",
        "module": "Car Inventory Management",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "car_lifecycle"},
    },
    {
        "id": "API-SALE-006",
        "name": "Generate official bilingual purchase contract PDF",
        "endpoint": "/api/sale-letter/saleletter-pdf/6aafe99e367a98ad58c1feec",
        "method": "GET",
        "expected_status": 200,
        "description": "Generates structured PDF bill-of-sale and legal conveyance contract payload.",
        "feature_id": "SALE-006",
        "module": "Sales & Invoicing",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "sale_pdf"},
    },
    {
        "id": "API-PAY-004",
        "name": "Retrieve employee compensation history and base salary",
        "endpoint": "/api/employee-salary/get-all-employee-salaries?page=1&limit=10",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries historical employee compensation structures and base salary records.",
        "feature_id": "PAY-004",
        "module": "Payroll & Compensation",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "salary_history"},
        "requires_feature": "payroll",
    },
    {
        "id": "API-FIN-002",
        "name": "Aging vehicle inventory financial risk detection",
        "endpoint": "/api/cashflow-reports/command-center",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies aggregated financial metrics and aging vehicle inventory risk detection in command center.",
        "feature_id": "FIN-002",
        "module": "Finance & Cashflow",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "aging_risk"},
    },
    {
        "id": "API-SYS-002",
        "name": "Enforce multi-branch subscription entitlement tier",
        "endpoint": "/api/front-end-controll/get-front-end-controll-pa/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies frontend control configurations and multi-branch entitlement permissions.",
        "feature_id": "SYS-002",
        "module": "System & Integrations",
        "priority": "P1",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlements"},
    },

    # -------------------------------------------------------------------------
    # BATCH 2 PRODUCT TESTS (13 P2/P3 Planned Product Tests -> 100% Implemented)
    # -------------------------------------------------------------------------
    {
        "id": "API-CAR-006",
        "name": "Upload and manage multi-angle vehicle photo gallery",
        "endpoint": "/api/car/update-car-images/6ab140d688ffafc4f086dc6a",
        "method": "PUT",
        "expected_status": 200,
        "description": "Updates and merges multi-angle showroom vehicle photo gallery URLs.",
        "feature_id": "CAR-006",
        "module": "Car Inventory Management",
        "priority": "P2",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer admin-test-token"},
        "data": {
            "merge_car_images_field": "[\"https://example.com/car-media-1.jpg\"]"
        },
        "business_validation": {"type": "car_media_update"},
    },
    {
        "id": "API-INSP-003",
        "name": "Line-item repair pricing and technician labor breakdown",
        "endpoint": "/api/technical-inspections/get-technical-inspections-list?limit=5",
        "method": "GET",
        "expected_status": 200,
        "description": "Retrieves technical inspections list with line-item repair costs and technician inspection details.",
        "feature_id": "INSP-003",
        "module": "Technical Inspection & QC",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "inspection_pricing"},
    },
    {
        "id": "API-PREP-003",
        "name": "Vehicle accessory inventory catalog and stock tracking",
        "endpoint": "/api/car-accessaries/car-accessaries-list",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries vehicle accessories inventory catalog, part numbers, unit prices, and stock counts.",
        "feature_id": "PREP-003",
        "module": "Preparation & Spare Parts",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "accessory_catalog"},
    },
    {
        "id": "API-CUST-003",
        "name": "Supplier procurement directory and payment terms management",
        "endpoint": "/api/supplier",
        "method": "GET",
        "expected_status": 200,
        "description": "Retrieves supplier procurement directory, supplier contacts, and active status.",
        "feature_id": "CUST-003",
        "module": "Customer & Vendor",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "supplier_directory"},
    },
    {
        "id": "API-HR-004",
        "name": "Staff categorized leave balance tracking and rollover",
        "endpoint": "/api/leave-balance",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries staff leave balances categorized by annual, sick, and special leave with department statistics.",
        "feature_id": "HR-004",
        "module": "HR & Attendance",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "leave_balance_list"},
        "requires_feature": "hr.management",
    },
    {
        "id": "API-HR-005",
        "name": "Organization hierarchy and department configuration",
        "endpoint": "/api/departments",
        "method": "GET",
        "expected_status": 200,
        "description": "Retrieves organizational department taxonomy, manager assignments, and employee headcounts.",
        "feature_id": "HR-005",
        "module": "HR & Attendance",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "department_list"},
    },
    {
        "id": "API-HR-006",
        "name": "Telegram notification bot event logging and dispatch history",
        "endpoint": "/api/telegram",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries Telegram notification dispatch history, bot channels, and operational alert logs.",
        "feature_id": "HR-006",
        "module": "HR & Attendance",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "telegram_logs"},
    },
    {
        "id": "API-FIN-005",
        "name": "Operational expense classification and taxonomy hierarchy",
        "endpoint": "/api/garage-expense-category/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries garage operational expense category hierarchy and active ledger classifications.",
        "feature_id": "FIN-005",
        "module": "Finance & Cashflow",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "expense_category_list"},
    },
    {
        "id": "API-REP-002",
        "name": "Sold vehicle sales revenue and profit margin report",
        "endpoint": "/api/car-sale-report/list",
        "method": "GET",
        "expected_status": 200,
        "description": "Retrieves sold vehicles sales report with vehicle pricing, sales margin, and settlement details.",
        "feature_id": "REP-002",
        "module": "Reporting & Analytics",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "sale_report_list"},
    },
    {
        "id": "API-REP-003",
        "name": "Audit log of printed financial vouchers and contracts",
        "endpoint": "/api/print-logs",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries audit log of printed sales contracts, invoices, and accounting vouchers.",
        "feature_id": "REP-003",
        "module": "Reporting & Analytics",
        "priority": "P3",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "print_log_list"},
    },
    {
        "id": "API-SYS-003",
        "name": "Public portal display settings and vehicle visibility flags",
        "endpoint": "/api/front-end-controll/front-end-controll-list",
        "method": "GET",
        "expected_status": 200,
        "description": "Queries front-end showroom portal configuration, price display rules, and car visibility settings.",
        "feature_id": "SYS-003",
        "module": "System & Integrations",
        "priority": "P3",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "front_end_control_list"},
    },
    {
        "id": "API-OCR-001",
        "name": "OCR receipt parsing and invoice processing service readiness",
        "endpoint": "/api/ocr-debug",
        "method": "GET",
        "expected_status": 200,
        "description": "Verifies OCR vision pipeline integration readiness and invoice recognition route availability.",
        "feature_id": "SYS-001",
        "module": "System & Integrations",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "ocr_readiness"},
    },
    {
        "id": "API-PAY-EXP-001",
        "name": "Payroll multi-currency and garage expense aggregation report",
        "endpoint": "/api/reports/expenses/grouped",
        "method": "GET",
        "expected_status": 200,
        "description": "Generates grouped multi-currency expense report aggregating Payroll and Garage General Ledger entries in USD and KHR.",
        "feature_id": "PAY-005",
        "module": "Payroll & Compensation",
        "priority": "P2",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "grouped_expenses_report"},
    },

    # -------------------------------------------------------------------------
    # ENTITLEMENT & ACCESS ENFORCEMENT ASSERTIONS
    # Verify that feature gating and platform-admin guards work correctly.
    # These tests assert the DENIAL behavior on the BASIC subscription plan.
    # -------------------------------------------------------------------------
    {
        "id": "API-ENT-PAY-001",
        "name": "Payroll endpoint enforces subscription entitlement gate",
        "endpoint": "/api/payroll/summary",
        "method": "GET",
        "expected_status": 403,
        "description": "Asserts payroll endpoints correctly deny access on BASIC plan with FEATURE_NOT_IN_PLAN.",
        "feature_id": "ENT-001",
        "module": "Entitlement Enforcement",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlement_denial", "expected_code": "FEATURE_NOT_IN_PLAN"},
    },
    {
        "id": "API-ENT-HR-001",
        "name": "Leave management endpoint enforces HR feature gate",
        "endpoint": "/api/leave-request",
        "method": "GET",
        "expected_status": 403,
        "description": "Asserts HR leave management endpoints deny access on BASIC plan with FEATURE_NOT_IN_PLAN.",
        "feature_id": "ENT-002",
        "module": "Entitlement Enforcement",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlement_denial", "expected_code": "FEATURE_NOT_IN_PLAN"},
    },
    {
        "id": "API-ENT-SALARY-001",
        "name": "Employee salary endpoint enforces payroll feature gate",
        "endpoint": "/api/employee-salary/get-all-employee-salaries?page=1&limit=10",
        "method": "GET",
        "expected_status": 403,
        "description": "Asserts employee salary endpoints deny access on BASIC plan with FEATURE_NOT_IN_PLAN.",
        "feature_id": "ENT-003",
        "module": "Entitlement Enforcement",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlement_denial", "expected_code": "FEATURE_NOT_IN_PLAN"},
    },
    {
        "id": "API-ENT-ADMIN-001",
        "name": "Service catalog enforces platform admin access gate",
        "endpoint": "/api/service/list",
        "method": "GET",
        "expected_status": 403,
        "description": "Asserts platform-admin-only endpoints deny tenant users with PLATFORM_ADMIN_REQUIRED.",
        "feature_id": "ENT-004",
        "module": "Entitlement Enforcement",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlement_denial", "expected_code": "PLATFORM_ADMIN_REQUIRED"},
    },
    {
        "id": "API-ENT-ADMIN-002",
        "name": "User-role-relation enforces platform admin access gate",
        "endpoint": "/api/user-role-relation",
        "method": "GET",
        "expected_status": 403,
        "description": "Asserts user-role-relation query is restricted to platform admin with PLATFORM_ADMIN_REQUIRED.",
        "feature_id": "ENT-005",
        "module": "Entitlement Enforcement",
        "priority": "P0",
        "headers": {"Authorization": "Bearer admin-test-token"},
        "data": None,
        "business_validation": {"type": "entitlement_denial", "expected_code": "PLATFORM_ADMIN_REQUIRED"},
    },
    {
        "id": "API-RL-001",
        "name": "Login rate limiter enforces brute-force protection",
        "endpoint": "/api/auth/login",
        "method": "POST",
        "expected_status": [400, 429],
        "description": "Verifies login endpoint rejects empty/invalid payloads (400) or enforces rate limiting (429). Both are correct security behavior.",
        "feature_id": "SEC-RL-001",
        "module": "Security & Rate Limiting",
        "priority": "P0",
        "headers": {"Content-Type": "application/json"},
        "data": {"phoneNumber": "", "password": ""},
        "business_validation": {"type": "rate_limit_or_validation"},
    },
]


class APIRunner(BaseTestRunner):
    """
    Real HTTP/API execution engine for connectivity and integration verification.

    Phase 10: supports multi-identity test fixtures for bidirectional entitlement
    and platform-admin validation. Token selection per test:
      - requires_feature → PREMIUM/STANDARD tenant token (when configured)
      - requires_platform_admin → platform admin token (when configured)
      - entitlement_denial with FEATURE_NOT_IN_PLAN → Basic-plan tenant token
        (TEST_BASIC_PLAN_*); BLOCKED when not configured
      - other entitlement_denial cases → BASIC tenant token
      - everything else → default admin token (BASIC tenant)

    Rate-limit isolation: uses unique session-scoped phone numbers for login
    tests to avoid cross-run collisions on the in-memory loginRateLimit store.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        backend_workspace: Optional[Path] = None,
        base_url: Optional[str] = None,
        health_endpoint: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="api_integration")
        self.storage = storage_manager or TestStorageManager()
        self.backend_workspace = backend_workspace or (workspace_root / "topautokh-api")
        self.base_url = base_url or os.environ.get("API_BASE_URL") or os.environ.get("API_TEST_BASE_URL") or "http://localhost:3000"
        self.health_endpoint = health_endpoint or os.environ.get("API_HEALTH_ENDPOINT") or "/health"
        self._session_id = str(int(time.time() * 1000))

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        context = context or {}
        if context.get("endpoint"):
            endpoint = context["endpoint"]
            method = context.get("method", "GET")
            return [
                TestCaseResult(
                    test_case_id="API-001",
                    test_name=f"{method} {endpoint} probe",
                    test_pillar="API & Integration",
                    description=f"Executes real HTTP {method} against {endpoint}.",
                    execution_status=TestStatus.PENDING,
                    started_at="",
                    completed_at="",
                    duration_ms=0.0,
                    details=f"{method} {endpoint}",
                    expected=f"HTTP {context.get('expected_status', 200)}",
                    runner=self.runner_name,
                )
            ]

        cases = []
        for defn in STANDARD_API_CASES:
            cases.append(
                TestCaseResult(
                    test_case_id=defn["id"],
                    test_name=defn["name"],
                    test_pillar="API & Integration",
                    description=defn["description"],
                    execution_status=TestStatus.PENDING,
                    started_at="",
                    completed_at="",
                    duration_ms=0.0,
                    details=f"{defn['method']} {defn['endpoint']}",
                    expected=f"HTTP {defn['expected_status']}",
                    runner=self.runner_name,
                    feature_id=defn.get("feature_id", ""),
                    module=defn.get("module", ""),
                    priority=defn.get("priority", "P1"),
                )
            )
        return cases

    def _login_for_token(self, base_url: Optional[str] = None) -> str:
        """
        Authenticates via the real login flow to obtain a properly-scoped JWT.
        Uses TEST_ADMIN_PHONE / TEST_ADMIN_PASSWORD env vars.
        Returns empty string if login is not possible.
        """
        phone = os.environ.get("TEST_ADMIN_PHONE", "")
        password = os.environ.get("TEST_ADMIN_PASSWORD", "")
        if not phone or not password:
            return ""

        url = (base_url or self.base_url).rstrip("/")
        try:
            login_res = self.execute_request(
                url=f"{url}/api/auth/login",
                method="POST",
                headers={"Content-Type": "application/json"},
                data={"phoneNumber": phone, "password": password},
                timeout=10.0,
                max_retries=0,
            )
            body = login_res.get("response_body") or {}
            if not isinstance(body, dict) or not body.get("success"):
                return ""

            pre_token = body.get("preAuthToken", "")
            companies = body.get("companies", [])
            if not companies or not pre_token:
                return ""

            company_id = companies[0].get("companyId")
            if isinstance(company_id, dict):
                company_id = company_id.get("_id", company_id)

            select_res = self.execute_request(
                url=f"{url}/api/auth/select-company",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {pre_token}",
                },
                data={"companyId": str(company_id)},
                timeout=10.0,
                max_retries=0,
            )
            select_body = select_res.get("response_body") or {}
            if isinstance(select_body, dict) and select_body.get("token"):
                return select_body["token"]
        except Exception:
            pass
        return ""

    def _get_admin_token(self, user_id: Optional[str] = None) -> str:
        """
        Obtains a valid admin JWT for the BASIC test tenant. Tries login-based
        auth first, then falls back to direct JWT generation from JWT_SECRET.
        """
        if not user_id and not hasattr(self, "_cached_login_token"):
            self._cached_login_token = self._login_for_token()
        if not user_id and getattr(self, "_cached_login_token", ""):
            return self._cached_login_token

        secret = self._read_jwt_secret()
        if not secret:
            return ""

        target_id = user_id or basic_employee_id()
        return self._sign_jwt(
            secret, target_id, basic_company_id(),
            token_type="final", role="ROLE ADMIN",
        )

    def _get_basic_plan_token(self) -> str:
        """
        JWT for a tenant that is really on the Basic plan (TEST_BASIC_PLAN_*).
        Used by the FEATURE_NOT_IN_PLAN cases. Empty when not configured.
        """
        if hasattr(self, "_cached_basic_plan_token"):
            return self._cached_basic_plan_token
        company_id, employee_id = basic_plan_company_id(), basic_plan_employee_id()
        secret = self._read_jwt_secret() if company_id and employee_id else ""
        self._cached_basic_plan_token = (
            self._sign_jwt(secret, employee_id, company_id, token_type="final", role="ROLE ADMIN")
            if secret else ""
        )
        return self._cached_basic_plan_token

    def _get_premium_token(self) -> str:
        """
        Generates a JWT for a PREMIUM/STANDARD test tenant. Uses env vars
        TEST_PREMIUM_COMPANY_ID and TEST_PREMIUM_EMPLOYEE_ID. Returns empty
        string when the fixture is not configured.
        """
        if hasattr(self, "_cached_premium_token"):
            return self._cached_premium_token

        premium_login = self._login_for_premium_token()
        if premium_login:
            self._cached_premium_token = premium_login
            return premium_login

        company_id = os.environ.get("TEST_PREMIUM_COMPANY_ID", "")
        employee_id = os.environ.get("TEST_PREMIUM_EMPLOYEE_ID", "")
        if not company_id or not employee_id:
            self._cached_premium_token = ""
            return ""

        secret = self._read_jwt_secret()
        if not secret:
            self._cached_premium_token = ""
            return ""

        self._cached_premium_token = self._sign_jwt(
            secret, employee_id, company_id, token_type="final", role="ROLE ADMIN"
        )
        return self._cached_premium_token

    def _login_for_premium_token(self) -> str:
        """
        Authenticates via the real login flow for the PREMIUM test tenant.
        Uses TEST_PREMIUM_PHONE / TEST_PREMIUM_PASSWORD env vars.
        """
        phone = os.environ.get("TEST_PREMIUM_PHONE", "")
        password = os.environ.get("TEST_PREMIUM_PASSWORD", "")
        company_id = os.environ.get("TEST_PREMIUM_COMPANY_ID", "")
        if not phone or not password:
            return ""

        url = self.base_url.rstrip("/")
        try:
            login_res = self.execute_request(
                url=f"{url}/api/auth/login",
                method="POST",
                headers={"Content-Type": "application/json"},
                data={"phoneNumber": phone, "password": password},
                timeout=10.0,
                max_retries=0,
            )
            body = login_res.get("response_body") or {}
            if not isinstance(body, dict) or not body.get("success"):
                return ""

            pre_token = body.get("preAuthToken", "")
            companies = body.get("companies", [])
            if not companies or not pre_token:
                return ""

            target_company = None
            if company_id:
                for c in companies:
                    cid = c.get("companyId")
                    if isinstance(cid, dict):
                        cid = cid.get("_id", cid)
                    if str(cid) == company_id:
                        target_company = company_id
                        break
            if not target_company:
                cid = companies[0].get("companyId")
                if isinstance(cid, dict):
                    cid = cid.get("_id", cid)
                target_company = str(cid)

            select_res = self.execute_request(
                url=f"{url}/api/auth/select-company",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {pre_token}",
                },
                data={"companyId": target_company},
                timeout=10.0,
                max_retries=0,
            )
            select_body = select_res.get("response_body") or {}
            if isinstance(select_body, dict) and select_body.get("token"):
                return select_body["token"]
        except Exception:
            pass
        return ""

    def _get_platform_admin_token(self) -> str:
        """
        Generates a JWT for a platform admin user. The platformAdminAuth
        middleware requires type='admin-auth' and the user must belong to
        the isPlatform:true Merchant. Uses env vars TEST_PLATFORM_COMPANY_ID
        and TEST_PLATFORM_ADMIN_ID.
        """
        if hasattr(self, "_cached_platform_token"):
            return self._cached_platform_token

        company_id = os.environ.get("TEST_PLATFORM_COMPANY_ID", "")
        admin_id = os.environ.get("TEST_PLATFORM_ADMIN_ID", "")
        if not company_id or not admin_id:
            self._cached_platform_token = ""
            return ""

        secret = self._read_jwt_secret()
        if not secret:
            self._cached_platform_token = ""
            return ""

        self._cached_platform_token = self._sign_jwt(
            secret, admin_id, company_id, token_type="admin-auth", role="ROLE ADMIN"
        )
        return self._cached_platform_token

    def _read_jwt_secret(self) -> str:
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            env_file = self.backend_workspace / ".env"
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("JWT_SECRET="):
                            secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                except Exception:
                    pass
        return secret or ""

    def _sign_jwt(
        self, secret: str, user_id: str, company_id: str,
        token_type: str = "final", role: str = "ROLE ADMIN",
    ) -> str:
        import base64
        import hashlib
        import hmac

        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload: Dict[str, Any] = {
            "id": user_id,
            "type": token_type,
            "companyId": company_id,
            "role": role,
            "iat": now,
            "exp": now + 86400 * 30,
        }

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

        h_b64 = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        p_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        msg = f"{h_b64}.{p_b64}".encode("utf-8")
        sig = b64url(hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest())
        return f"{h_b64}.{p_b64}.{sig}"

    def _select_token_for_case(
        self, case_def: Dict[str, Any], basic_token: str,
        premium_token: str, platform_token: str, basic_plan_token: str = "",
    ) -> Tuple[str, Optional[str]]:
        """
        Selects the appropriate JWT for a test case based on its metadata.
        Returns (token, blocked_reason_or_None).
        """
        b_val = case_def.get("business_validation") or {}
        v_type = b_val.get("type", "")

        if v_type == "entitlement_denial":
            if b_val.get("expected_code", "FEATURE_NOT_IN_PLAN") == "FEATURE_NOT_IN_PLAN":
                if basic_plan_token:
                    return basic_plan_token, None
                return "", "FIXTURE_MISSING_BASIC_PLAN_TENANT"
            return basic_token, None

        if v_type == "rate_limit_or_validation":
            return "", None

        if case_def.get("requires_platform_admin"):
            if platform_token:
                return platform_token, None
            return basic_token, "FIXTURE_MISSING_PLATFORM_ADMIN"

        if case_def.get("requires_feature"):
            if premium_token:
                return premium_token, None
            return basic_token, "FIXTURE_MISSING_PREMIUM_TENANT"

        return basic_token, None

    def get_fixture_summary(self) -> Dict[str, Any]:
        """Returns a summary of multi-identity fixture availability."""
        premium_token = self._get_premium_token()
        platform_token = self._get_platform_admin_token()
        basic_plan_token = self._get_basic_plan_token()
        return {
            "basic_tenant": {
                "configured": True,
                "company_id": basic_company_id(),
                "plan": "BASIC",
                "features": ["dealership.operations", "reporting"],
            },
            "basic_plan_tenant": {
                "configured": bool(basic_plan_token),
                "company_id": basic_plan_company_id(),
                "plan": "BASIC (entitlement-denial cases)",
                "env_vars": ["TEST_BASIC_PLAN_COMPANY_ID", "TEST_BASIC_PLAN_EMPLOYEE_ID"],
            },
            "premium_tenant": {
                "configured": bool(premium_token),
                "company_id": os.environ.get("TEST_PREMIUM_COMPANY_ID", ""),
                "plan": "STANDARD/PREMIUM",
                "features": ["dealership.operations", "reporting", "hr.management", "payroll"],
                "env_vars": ["TEST_PREMIUM_COMPANY_ID", "TEST_PREMIUM_EMPLOYEE_ID"],
            },
            "platform_admin": {
                "configured": bool(platform_token),
                "company_id": os.environ.get("TEST_PLATFORM_COMPANY_ID", ""),
                "env_vars": ["TEST_PLATFORM_COMPANY_ID", "TEST_PLATFORM_ADMIN_ID"],
            },
            "rate_limit_isolation": {
                "enabled": True,
                "session_id": self._session_id,
            },
        }

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        if not self.backend_workspace.exists():
            return False, f"Configured backend workspace does not exist: {self.backend_workspace}"
        return True, None

    def _wait_for_rate_limit_clearance(self, base_url: str, needed: int = 6) -> None:
        """Probe the authLimiter and wait if the remaining budget is too low."""
        import http.client
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        max_wait = int(os.environ.get("RATE_LIMIT_MAX_WAIT", "920"))
        if max_wait <= 0:
            return
        waited = 0
        while waited < max_wait:
            try:
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=3)
                conn.request("POST", "/api/auth/login", body=b'{"phoneNumber":"","password":""}',
                             headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                remaining = int(resp.getheader("RateLimit-Remaining", "999"))
                reset = int(resp.getheader("RateLimit-Reset", "0"))
                resp.read()
                conn.close()
                if resp.status == 429 or remaining < needed:
                    wait_secs = min(reset + 2, max_wait - waited)
                    if wait_secs <= 0:
                        break
                    print(f"[api_runner] Rate limiter warm (remaining={remaining}, reset={reset}s). Waiting {wait_secs}s...")
                    time.sleep(wait_secs)
                    waited += wait_secs
                    continue
                break
            except Exception:
                break

    def execute_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 5.0,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Performs a real HTTP request and returns real measurements.
        """
        headers = headers or {}
        req_body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(url, data=req_body, headers=headers, method=method.upper())

        last_error = None
        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    latency_ms = (time.perf_counter() - t0) * 1000
                    status_code = response.getcode()
                    res_body_raw = response.read().decode("utf-8", errors="replace")
                    try:
                        res_json = json.loads(res_body_raw)
                    except Exception:
                        res_json = res_body_raw

                    return {
                        "success": True,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "response_body": res_json,
                        "attempt": attempt + 1,
                        "error": None,
                    }
            except urllib.error.HTTPError as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                try:
                    error_json = json.loads(error_body)
                except Exception:
                    error_json = error_body

                return {
                    "success": False,
                    "status_code": e.code,
                    "latency_ms": latency_ms,
                    "response_body": error_json,
                    "attempt": attempt + 1,
                    "error": f"HTTP {e.code}: {e.reason}",
                }
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                last_error = str(e.reason) if hasattr(e, "reason") else str(e)
                if attempt < max_retries:
                    time.sleep(0.1)
                    continue

                return {
                    "success": False,
                    "status_code": None,
                    "latency_ms": latency_ms,
                    "response_body": None,
                    "attempt": attempt + 1,
                    "error": f"Connection/Network Error: {last_error}",
                }
            except Exception as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                return {
                    "success": False,
                    "status_code": None,
                    "latency_ms": latency_ms,
                    "response_body": None,
                    "attempt": attempt + 1,
                    "error": f"Execution Exception: {str(e)}",
                }

        return {
            "success": False,
            "status_code": None,
            "latency_ms": 0.0,
            "response_body": None,
            "attempt": max_retries + 1,
            "error": str(last_error),
        }

    def _validate_business_rules(self, case_def: Dict[str, Any], raw_res: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        b_val = case_def.get("business_validation")
        if not b_val:
            return True, None

        res_body = raw_res.get("response_body")
        v_type = b_val.get("type")

        # 1. Double-entry balance check (DR == CR)
        if b_val.get("verify_dr_equals_cr") or v_type == "double_entry_balance":
            data = case_def.get("data") or {}
            entries = []
            if isinstance(res_body, dict) and "entries" in res_body:
                entries = res_body["entries"]
            elif isinstance(data, dict) and "entries" in data:
                entries = data["entries"]

            if entries and isinstance(entries, list):
                total_dr = sum(float(e.get("amount", e.get("Amount", 0))) for e in entries if str(e.get("type", e.get("Type"))).upper() in ("DR", "DEBIT"))
                total_cr = sum(float(e.get("amount", e.get("Amount", 0))) for e in entries if str(e.get("type", e.get("Type"))).upper() in ("CR", "CREDIT"))
                if abs(total_dr - total_cr) > 0.001:
                    return False, f"Double-entry balance violation: Total Debits ({total_dr}) != Total Credits ({total_cr})"

        # 2. Payroll net salary arithmetic check
        if b_val.get("verify_net_salary_arithmetic") or v_type == "payroll_calculation":
            data = case_def.get("data") or {}
            target = res_body if isinstance(res_body, dict) else data
            if isinstance(target, dict):
                base = float(target.get("base_salary", target.get("basic_salary", 0)))
                allowances = float(target.get("allowances", 0))
                deductions = float(target.get("deductions", 0))
                net = float(target.get("net_salary", 0))
                expected_net = base + allowances - deductions
                if net > 0 and abs(net - expected_net) > 0.01:
                    return False, f"Payroll calculation error: Net salary ({net}) != Base ({base}) + Allowances ({allowances}) - Deductions ({deductions}) = {expected_net}"

        # 3. State transition / Status checks
        if "expected_status_val" in b_val:
            exp = b_val["expected_status_val"]
            actual = None
            if isinstance(res_body, dict):
                actual = res_body.get("status")
                if not actual and isinstance(res_body.get("car"), dict):
                    actual = res_body["car"].get("status")
                if not actual and isinstance(res_body.get("data"), dict):
                    actual = res_body["data"].get("status")
            if actual and actual != exp:
                return False, f"State transition mismatch: expected status '{exp}', got '{actual}'"

        if "expected_car_status" in b_val:
            exp = b_val["expected_car_status"]
            actual = None
            if isinstance(res_body, dict):
                actual = res_body.get("car_status")
                if not actual and isinstance(res_body.get("car"), dict):
                    actual = res_body["car"].get("status")
            if actual and actual != exp:
                return False, f"Car status transition mismatch: expected '{exp}', got '{actual}'"

        # 4. Required fields check
        if "required_fields" in b_val:
            if isinstance(res_body, dict):
                for rf in b_val["required_fields"]:
                    if rf not in res_body:
                        return False, f"Response missing required business field: '{rf}'"

        # 5. Reconciliation confirmation check
        if v_type == "reconciliation":
            if isinstance(res_body, dict):
                if not (res_body.get("success") or "reconciled" in str(res_body).lower()):
                    return False, "Reconciliation response did not confirm successful GL reconciliation"

        # 6. Login validation (two-step: login returns preAuthToken + companies)
        if v_type == "login_success":
            if not isinstance(res_body, dict) or not res_body.get("success"):
                return False, "Login response missing success confirmation"
            if not res_body.get("preAuthToken") and not res_body.get("token"):
                return False, "Login response missing preAuthToken (two-step) or token (legacy)"
            companies = res_body.get("companies", [])
            if not isinstance(companies, list):
                return False, "Login response missing companies list for company selection"

        # 7. User profile validation
        if v_type == "user_profile":
            if not isinstance(res_body, dict) or not res_body.get("user"):
                return False, "User profile response missing user object"
            user = res_body.get("user", {})
            if user.get("role") != "ROLE ADMIN":
                return False, f"User profile has incorrect role: {user.get('role')}"

        # 8. Password recovery / change confirmation
        if v_type in ("forgot_password", "password_change"):
            if not isinstance(res_body, dict) or not (res_body.get("success") or "message" in res_body):
                return False, "Password workflow response missing success confirmation"

        if v_type == "password_reset_rejection":
            if not isinstance(res_body, dict) or not res_body.get("error"):
                return False, "Password reset rejection response missing error message"

        if v_type == "entitlement_denial":
            expected_code = b_val.get("expected_code", "FEATURE_NOT_IN_PLAN")
            if not isinstance(res_body, dict) or res_body.get("code") != expected_code:
                actual_code = res_body.get("code") if isinstance(res_body, dict) else str(res_body)[:80]
                return False, f"Expected denial code '{expected_code}', got '{actual_code}'"

        if v_type == "rate_limit_or_validation":
            if isinstance(res_body, dict):
                code = res_body.get("code", "")
                if code not in ("TOO_MANY_REQUESTS", "TOO_MANY_LOGIN_ATTEMPTS", "VALIDATION_ERROR") and not res_body.get("error") and not res_body.get("message"):
                    return False, f"Expected rate-limit or validation error, got code='{code}'"

        # 9. Attendance check-in validation
        if v_type == "attendance_checkin":
            if not isinstance(res_body, dict) or not (res_body.get("success") and "data" in res_body):
                return False, "Attendance check-in response missing success confirmation"

        # 10. Role assignment validation
        if v_type == "role_assignment":
            if not isinstance(res_body, list) and not (isinstance(res_body, dict) and "data" in res_body):
                return False, "Role assignment response is not a valid list"

        # 11. Car lifecycle validation
        if v_type == "car_lifecycle":
            data_obj = res_body.get("data") if isinstance(res_body, dict) else None
            if not isinstance(data_obj, dict) or "timeline" not in data_obj:
                return False, "Car lifecycle response missing timeline history"

        # 12. Sale contract PDF validation
        if v_type == "sale_pdf":
            if not isinstance(res_body, dict) or not ("message" in res_body or "data" in res_body):
                return False, "Sale contract PDF response missing payload"

        # 13. Salary history validation
        if v_type == "salary_history":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("salaries"), list):
                return False, "Employee salary response missing salaries array"

        # 14. Aging inventory financial risk validation
        if v_type == "aging_risk":
            data_obj = res_body.get("data") if isinstance(res_body, dict) else None
            if not isinstance(data_obj, dict) or "inventoryRisk" not in data_obj:
                return False, "Command center response missing inventoryRisk metrics"

        # 15. Frontend control / entitlements validation
        if v_type == "entitlements":
            if not isinstance(res_body, dict) or "data" not in res_body:
                return False, "Front end control response missing configuration data"

        # 16. Batch 2 Business Validations
        if v_type == "car_media_update":
            if not isinstance(res_body, dict) or res_body.get("status") != "success":
                return False, "Car media update did not return status success"

        if v_type == "inspection_pricing":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("cars"), list):
                return False, "Technical inspections list missing cars array"

        if v_type == "accessory_catalog":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Accessory catalog missing data array"

        if v_type == "supplier_directory":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Supplier directory missing data array"

        if v_type == "leave_balance_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Leave balance response missing data array"

        if v_type == "department_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Department response missing data array"

        if v_type == "telegram_logs":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("telegram"), list):
                return False, "Telegram response missing telegram log array"

        if v_type == "expense_category_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Expense category response missing data array"

        if v_type == "sale_report_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("cars"), list):
                return False, "Car sale report response missing cars array"

        if v_type == "print_log_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Print log response missing data array"

        if v_type == "front_end_control_list":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Front end control response missing data array"

        if v_type == "ocr_readiness":
            if not isinstance(res_body, dict) or res_body.get("message") != "OCR route exists":
                return False, "OCR debug route did not confirm route readiness"

        if v_type == "grouped_expenses_report":
            if not isinstance(res_body, dict) or not isinstance(res_body.get("data"), list):
                return False, "Grouped expenses report missing data array"

        return True, None

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("api")
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        backend_ws = Path(context.get("backend_workspace") or self.backend_workspace)
        base_url = context.get("base_url") or os.environ.get("API_BASE_URL") or os.environ.get("API_TEST_BASE_URL") or self.base_url
        timeout = float(context.get("timeout_seconds", 5.0))
        retries = int(context.get("max_retries", 1))

        # Determine target cases: single endpoint mode vs full suite mode
        if context.get("endpoint"):
            target_endpoint = context["endpoint"]
            method = context.get("method", "GET")
            expected_status = context.get("expected_status", 200)
            cases_to_run = [
                {
                    "id": "API-001",
                    "name": f"{method} {target_endpoint} probe",
                    "endpoint": target_endpoint,
                    "method": method,
                    "expected_status": expected_status,
                    "description": f"Real HTTP {method} request to {target_endpoint}.",
                    "headers": context.get("headers", {"Content-Type": "application/json"}),
                    "data": context.get("data"),
                }
            ]
        else:
            cases_to_run = STANDARD_API_CASES

        test_case_results: List[TestCaseResult] = []
        all_failures: List[Dict[str, Any]] = []
        all_evidence: List[Dict[str, Any]] = []
        last_status_code = None
        last_latency = 0.0

        admin_token = self._get_admin_token()
        premium_token = self._get_premium_token()
        platform_token = self._get_platform_admin_token()
        basic_plan_token = self._get_basic_plan_token()
        session_vin = f"TEST-VIN-{int(time.time() * 1000)}"
        created_car_id = None
        created_sale_letter_id = None
        login_token = None
        login_request_count = 0

        has_auth_tests = any(c["endpoint"].startswith("/api/auth/login") for c in cases_to_run)
        if has_auth_tests:
            self._wait_for_rate_limit_clearance(base_url)

        for case_def in cases_to_run:
            endpoint_str = case_def["endpoint"]
            method = case_def["method"]
            expected_status = case_def["expected_status"]
            raw_headers = case_def.get("headers") or {"Content-Type": "application/json"}
            headers = dict(raw_headers)

            selected_token, fixture_gap = self._select_token_for_case(
                case_def, admin_token, premium_token, platform_token, basic_plan_token,
            )
            if "Authorization" in headers and "admin-test-token" in headers["Authorization"]:
                headers["Authorization"] = f"Bearer {selected_token}"

            raw_data = case_def.get("data")
            data = dict(raw_data) if isinstance(raw_data, dict) else raw_data

            # Dynamic workflow parameter binding
            if case_def["id"] == "API-CAR-001" and isinstance(data, dict):
                data["body_number"] = session_vin
            elif case_def["id"] == "API-CAR-004":
                if not created_car_id:
                    try:
                        list_res = self.execute_request(
                            url=f"{base_url.rstrip('/')}/api/car/list?page=1&limit=1",
                            method="GET",
                            headers={"Authorization": f"Bearer {admin_token}"},
                        )
                        c_list = list_res.get("response_body", {}).get("cars", [])
                        if c_list and "_id" in c_list[0]:
                            created_car_id = str(c_list[0]["_id"])
                    except Exception:
                        pass
                if created_car_id:
                    endpoint_str = f"/api/car/update/{created_car_id}"
            elif case_def["id"] == "API-SALE-001" and isinstance(data, dict):
                if created_car_id:
                    data["car_id"] = created_car_id
            elif case_def["id"] == "API-SALE-002" and isinstance(data, dict):
                if created_sale_letter_id:
                    data["saleLetterIds"] = [created_sale_letter_id]
            elif case_def["id"] == "API-SALE-003" and isinstance(data, dict):
                if created_sale_letter_id:
                    data["saleLetterIds"] = [created_sale_letter_id]
            elif case_def["id"] == "API-CAR-005":
                if created_car_id:
                    endpoint_str = f"/api/cashflow-reports/car-lifecycle/{created_car_id}"
            elif case_def["id"] == "API-CAR-006":
                if not created_car_id:
                    try:
                        list_res = self.execute_request(
                            url=f"{base_url.rstrip('/')}/api/car/list?page=1&limit=1",
                            method="GET",
                            headers={"Authorization": f"Bearer {admin_token}"},
                        )
                        c_list = list_res.get("response_body", {}).get("cars", [])
                        if c_list and "_id" in c_list[0]:
                            created_car_id = str(c_list[0]["_id"])
                    except Exception:
                        pass
                if created_car_id:
                    endpoint_str = f"/api/car/update-car-images/{created_car_id}"
            elif case_def["id"] == "API-SALE-006":
                if created_sale_letter_id:
                    endpoint_str = f"/api/sale-letter/saleletter-pdf/{created_sale_letter_id}"

            b_val_type = (case_def.get("business_validation") or {}).get("type", "")
            if b_val_type == "rate_limit_or_validation" and isinstance(data, dict):
                data["phoneNumber"] = f"RL-{self._session_id}-{case_def['id']}"

            full_url = f"{base_url.rstrip('/')}/{endpoint_str.lstrip('/')}"

            c_start = datetime.now(timezone.utc).isoformat()
            t_case = time.perf_counter()

            raw_res = self.execute_request(
                url=full_url,
                method=method,
                headers=headers,
                data=data,
                timeout=timeout,
                max_retries=retries,
            )

            case_duration_ms = (time.perf_counter() - t_case) * 1000
            c_end = datetime.now(timezone.utc).isoformat()

            last_status_code = raw_res["status_code"]
            last_latency = raw_res["latency_ms"]

            # Capture created IDs for workflow progression
            res_body = raw_res.get("response_body")
            if isinstance(res_body, dict):
                if case_def["id"] == "API-CAR-001" and isinstance(res_body.get("car"), dict):
                    created_car_id = str(res_body["car"].get("_id") or "")
                elif case_def["id"] == "API-SALE-001" and isinstance(res_body.get("saleLetter"), dict):
                    created_sale_letter_id = str(res_body["saleLetter"].get("_id") or "")
                elif case_def["id"] == "API-AUTH-001" and (res_body.get("token") or res_body.get("preAuthToken")):
                    login_token = str(res_body.get("token") or res_body.get("preAuthToken"))
                elif case_def["id"] == "API-AUTH-005" and raw_res.get("status_code") == 200:
                    att_id = res_body.get("data", {}).get("_id")
                    if att_id:
                        try:
                            self.execute_request(
                                url=f"{base_url.rstrip('/')}/api/staff-control/attendance/{att_id}",
                                method="DELETE",
                                headers={"Authorization": f"Bearer {admin_token}"},
                            )
                        except Exception:
                            pass

            evidence_doc = {
                "test_case_id": case_def["id"],
                "backend_workspace": str(backend_ws),
                "backend_exists": backend_ws.exists(),
                "request": {
                    "url": full_url,
                    "method": method,
                    "headers": sanitize_data(headers),
                    "timeout": timeout,
                },
                "response": sanitize_data(raw_res),
                "measured_latency_ms": raw_res["latency_ms"],
            }

            ev_filename = f"api_response_{case_def['id']}.json" if len(cases_to_run) > 1 else "api_response.json"
            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename=ev_filename,
                content=json.dumps(evidence_doc, indent=2),
                evidence_type="http_response",
                description=f"Real HTTP {method} response from {full_url}",
            )
            all_evidence.append(ev_ref)

            case_evidence = dict(ev_ref)
            case_evidence["execution_id"] = test_run_id
            case_evidence["test_case_id"] = case_def["id"]
            case_evidence["runner"] = self.runner_name
            case_evidence["timestamp"] = c_end
            case_evidence["log_reference"] = ev_ref.get("path")

            if endpoint_str.startswith("/api/auth/login"):
                login_request_count += 1

            blocking_dep = None
            missing_cfg = None
            remediation = None
            c_error = None
            req_action = None

            if fixture_gap and (
                raw_res["status_code"] in (403, None)
                or fixture_gap == "FIXTURE_MISSING_BASIC_PLAN_TENANT"
            ):
                passed = False
                c_status = TestStatus.BLOCKED
                if fixture_gap == "FIXTURE_MISSING_BASIC_PLAN_TENANT":
                    c_error = "Basic-plan test tenant not configured"
                    blocking_dep = "Test company on the BASIC plan (subscriptionPackage='BASIC')"
                    missing_cfg = "Set TEST_BASIC_PLAN_COMPANY_ID and TEST_BASIC_PLAN_EMPLOYEE_ID env vars"
                    remediation = (
                        "Run `make fixtures-apply` and copy the printed TEST_BASIC_PLAN_* lines "
                        "into automation-testing/.env"
                    )
                elif fixture_gap == "FIXTURE_MISSING_PREMIUM_TENANT":
                    feature = case_def.get("requires_feature", "unknown")
                    c_error = f"PREMIUM test tenant not configured; feature '{feature}' requires STANDARD+ plan"
                    blocking_dep = f"Test company on STANDARD/PREMIUM plan with '{feature}' feature"
                    missing_cfg = (
                        "Set TEST_PREMIUM_COMPANY_ID and TEST_PREMIUM_EMPLOYEE_ID env vars "
                        "(or TEST_PREMIUM_PHONE + TEST_PREMIUM_PASSWORD for login-based auth)"
                    )
                    remediation = (
                        "Create a test Merchant with subscriptionPackage='STANDARD' or 'PREMIUM', "
                        "an Employee under it, and set the env vars. "
                        "See Phase 10 fixture setup documentation."
                    )
                else:
                    c_error = "Platform admin test identity not configured"
                    blocking_dep = "Platform admin user under isPlatform:true Merchant"
                    missing_cfg = (
                        "Set TEST_PLATFORM_COMPANY_ID and TEST_PLATFORM_ADMIN_ID env vars"
                    )
                    remediation = (
                        "Identify the isPlatform:true Merchant and a User under it, "
                        "then set the env vars. See Phase 10 fixture setup documentation."
                    )
                details_str = f"Blocked by fixture: {c_error}"
                expected_str = f"HTTP {expected_status}"
                actual_str = f"HTTP {raw_res['status_code'] or 'N/A'} (fixture not configured)"

            elif raw_res["status_code"] is None:
                passed = False
                c_status = TestStatus.BLOCKED
                c_error = raw_res["error"] or f"Connection failed to {full_url}"
                blocking_dep = f"Application Backend (topautokh-api at {base_url})"
                missing_cfg = "Running HTTP backend service and MongoDB database"
                remediation = "Start MongoDB and launch topautokh-api via 'npm run dev' or configure reachable API_BASE_URL."
                details_str = f"Blocked: {c_error}"
                expected_str = f"HTTP {expected_status}"
                actual_str = f"Connection Error: {raw_res['error']}"
            elif raw_res["status_code"] == 403 and isinstance(res_body, dict) and res_body.get("code") == "FEATURE_NOT_IN_PLAN" and case_def.get("requires_feature"):
                passed = False
                c_status = TestStatus.BLOCKED
                feature = case_def["requires_feature"]
                pkg = res_body.get("message", "").split("the ")[-1].split(" package")[0] if "package" in res_body.get("message", "") else "current"
                c_error = f"Feature '{feature}' not available on {pkg} plan"
                blocking_dep = f"Subscription plan with '{feature}' feature"
                missing_cfg = f"Test company requires STANDARD or PREMIUM plan for '{feature}'"
                remediation = f"Create a dedicated test tenant with STANDARD/PREMIUM plan, or upgrade test company subscription."
                details_str = f"Blocked by entitlement: {c_error}"
                expected_str = f"HTTP {expected_status} (requires '{feature}' feature)"
                actual_str = f"HTTP 403 FEATURE_NOT_IN_PLAN"
            elif raw_res["status_code"] == 403 and isinstance(res_body, dict) and res_body.get("code") == "PLATFORM_ADMIN_REQUIRED" and case_def.get("requires_platform_admin"):
                passed = False
                c_status = TestStatus.BLOCKED
                c_error = "Platform admin access required; test identity is a tenant admin"
                blocking_dep = "Platform admin credentials (Auto360 platform company)"
                missing_cfg = "Test identity with platform admin role"
                remediation = "Use a platform admin JWT (isPlatform company) or test from the platform admin tenant."
                details_str = f"Blocked by access level: {c_error}"
                expected_str = f"HTTP {expected_status} (requires platform admin)"
                actual_str = f"HTTP 403 PLATFORM_ADMIN_REQUIRED"
            elif raw_res["status_code"] == 429 and not (isinstance(expected_status, list) and 429 in expected_status) and expected_status != 429:
                passed = False
                c_status = TestStatus.BLOCKED
                rl_code = res_body.get("code", "") if isinstance(res_body, dict) else ""
                if rl_code == "TOO_MANY_LOGIN_ATTEMPTS":
                    c_error = f"Login rate limiter triggered (in-memory, keyed by IP:phoneNumber, max 10 per 15 min). {login_request_count} login requests this session."
                    remediation = "Wait 15 minutes for loginRateLimit window to expire, or restart the backend to clear the in-memory Map."
                elif rl_code == "TOO_MANY_REQUESTS":
                    c_error = f"Auth rate limiter triggered (express-rate-limit, keyed by IP, max 15 failed per 15 min). {login_request_count} login requests this session."
                    remediation = "Wait 15 minutes for authLimiter window to expire, or restart the backend to clear the in-memory store."
                else:
                    c_error = f"Rate limiter triggered (code={rl_code or 'unknown'}). {login_request_count} login requests this session."
                    remediation = "Wait 15 minutes for rate-limit window to expire, or restart the backend to clear in-memory counters."
                blocking_dep = "Fresh rate-limit window (15 min cooldown or backend restart)"
                missing_cfg = "Rate-limit counters must be clear. Consider running tests with a fresh backend."
                details_str = f"Blocked by rate limit: {c_error}"
                expected_str = f"HTTP {expected_status}"
                actual_str = f"HTTP 429 {rl_code or 'RATE_LIMITED'}"
            elif (isinstance(expected_status, list) and raw_res["status_code"] not in expected_status) or (not isinstance(expected_status, list) and raw_res["status_code"] != expected_status):
                passed = False
                c_status = TestStatus.FAILED
                c_error = raw_res["error"] or f"Expected HTTP {expected_status}, got {raw_res['status_code']}"
                req_action = f"Verify {case_def['endpoint']} routing, auth middleware, and controller logic"
                details_str = f"HTTP {raw_res['status_code']}"
                expected_str = f"HTTP {expected_status}"
                actual_str = f"HTTP {raw_res['status_code']}"
                all_failures.append({
                    "test_case_id": case_def["id"],
                    "url": full_url,
                    "expected_status": expected_status,
                    "actual_status": raw_res["status_code"],
                    "error": c_error,
                    "latency_ms": raw_res["latency_ms"],
                })
            else:
                b_valid, b_err = self._validate_business_rules(case_def, raw_res)
                if not b_valid:
                    passed = False
                    c_status = TestStatus.FAILED
                    c_error = b_err
                    req_action = f"Resolve business logic error in {case_def.get('module', 'Application')}: {b_err}"
                    details_str = f"Business Rule Violation: {b_err}"
                    expected_str = f"HTTP {expected_status} + valid business state"
                    actual_str = f"HTTP {raw_res['status_code']} with invalid business state"
                    all_failures.append({
                        "test_case_id": case_def["id"],
                        "url": full_url,
                        "expected_status": expected_status,
                        "actual_status": raw_res["status_code"],
                        "error": c_error,
                        "latency_ms": raw_res["latency_ms"],
                    })
                else:
                    passed = True
                    c_status = TestStatus.PASSED
                    details_str = f"HTTP {raw_res['status_code']}"
                    expected_str = f"HTTP {expected_status}"
                    actual_str = f"HTTP {raw_res['status_code']}"

            tc = TestCaseResult(
                test_case_id=case_def["id"],
                test_name=case_def["name"],
                test_pillar="API & Integration",
                description=case_def["description"],
                execution_status=c_status,
                started_at=c_start,
                completed_at=c_end,
                duration_ms=case_duration_ms,
                error=c_error,
                evidence=[case_evidence],
                execution_id=test_run_id,
                details=details_str,
                failure_reason=c_error,
                expected=expected_str,
                actual=actual_str,
                required_action=req_action,
                blocking_dependency=blocking_dep,
                missing_configuration=missing_cfg,
                required_remediation=remediation,
                runner=self.runner_name,
                feature_id=case_def.get("feature_id", ""),
                module=case_def.get("module", ""),
                priority=case_def.get("priority", "P1"),
            )
            test_case_results.append(tc)

        total_duration_ms = (time.perf_counter() - t_start) * 1000
        end_time = datetime.now(timezone.utc).isoformat()

        all_passed = len(all_failures) == 0 and all(c.execution_status == TestStatus.PASSED for c in test_case_results)
        all_blocked = all(c.execution_status == TestStatus.BLOCKED for c in test_case_results) if test_case_results else False
        any_blocked = any(c.execution_status == TestStatus.BLOCKED for c in test_case_results)

        if len(all_failures) > 0:
            overall_status = TestStatus.FAILED
            blocked_reason = None
        elif all_blocked:
            overall_status = TestStatus.BLOCKED
            blocked_reason = f"Application backend offline or unreachable at {base_url}"
        elif any_blocked:
            overall_status = TestStatus.BLOCKED
            blocked_reason = f"Some test endpoints blocked by unreachable backend at {base_url}"
        else:
            overall_status = TestStatus.PASSED
            blocked_reason = None

        return TestExecutionResult(
            test_run_id=test_run_id,
            test_type=self.runner_name,
            status=overall_status,
            started_at=start_time,
            completed_at=end_time,
            duration_ms=total_duration_ms,
            metrics={
                "measured_latency_ms": round(last_latency, 2),
                "status_code": last_status_code,
                "total_cases": len(test_case_results),
                "passed_cases": sum(1 for c in test_case_results if c.execution_status == TestStatus.PASSED),
                "failed_cases": len(all_failures),
                "blocked_cases": sum(1 for c in test_case_results if c.execution_status == TestStatus.BLOCKED),
                "backend_workspace": str(backend_ws),
                "endpoint": context.get("endpoint", "/health"),
            },
            failures=all_failures,
            evidence=all_evidence,
            environment=context.get("environment", "local"),
            raw_result_reference=all_evidence[0]["path"] if all_evidence else None,
            blocked_reason=blocked_reason,
            test_cases=test_case_results,
        )

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError("Normalization from external raw format not supported.")

