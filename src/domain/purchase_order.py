from typing import List, Optional
from datetime import date as Date
from pydantic import BaseModel, Field

class GstGrouping(BaseModel):
    gstPercentage: str
    amount: float
    gstType: str
    ledgerId: int

class LineItem(BaseModel):
    productId: int
    productName: str
    description: Optional[str] = None
    hsnCode: Optional[str] = None
    unitType: Optional[str] = None
    quantity: float
    discount: float
    unitPrice: float
    amount: float
    gst: float
    totalAmount: float
    grnId: Optional[int] = None
    storeId: Optional[int] = None
    typeOfService: Optional[str] = None

class ShippingDetails(BaseModel):
    documentNo: Optional[str] = None
    dispatchThrough: Optional[str] = None
    destination: Optional[str] = None
    carrierName: Optional[str] = None
    lrOrRrNo: Optional[str] = None
    vehicleNo: Optional[str] = None
    eWayBillNo: Optional[str] = None
    ewayBillDate: Optional[Date] = None

class PurchaseOrder(BaseModel):
    voucherType: str
    supplierInvoiceNo: Optional[str] = None
    date: Date | None = None
    status: Optional[str] = None
    partyLedgerId: int
    purchaseLedgerId: int
    partyAddress: Optional[str] = None
    billingAddress: Optional[str] = None
    billingState: Optional[str] = None
    shippingAddress: Optional[str] = None
    shippingState: Optional[str] = None
    gstType: str
    grnIds: List[int] = Field(default_factory=list)
    storeIds: List[int] = Field(default_factory=list)
    awsFileId: Optional[str] = None
    amount: float
    gstAmount: float
    gstGroupings: List[GstGrouping] = Field(default_factory=list)
    lineItems: List[LineItem] = Field(default_factory=list)
    shippingDetails: Optional[ShippingDetails] = None
