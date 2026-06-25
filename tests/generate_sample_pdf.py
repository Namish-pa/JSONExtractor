"""
Generates a sample Purchase Invoice PDF matching the image provided by the user.
Uses PyMuPDF (already installed) to create the PDF.
"""
import fitz  # PyMuPDF

def generate_invoice_pdf(output_path: str):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    invoice_text = """PTG Complex
Jayanagar 5th block, near Raghavendraswamy Mutt
Bengaluru, Karnataka, India - 560041
Phone: 9876543212 | Email: arivu@gmail.com

                    PURCHASE INVOICE

Vendor Address:
15, Bannerghatta Rd, opp. Shoppers Stop, Sarakki
Industrial Layout, 3rd Phase, J. P. Nagar, Bengaluru,
Karnataka 560078

Shipping Address:
PTG
Jayanagar 6th block, near Raghavendraswamy Mutt
Bengaluru, Karnataka, 560041

Shipping Details:
Delivery Challan No    : N/A
Delivery Challan Date  : N/A
Document No            : DN-210
Dispatch Through       : Courier
Destination            : Bangalore, south
Carrier Name           : VRI
LR / RR No             : REC-2190
Vehicle No             : KA-01-AB-2190
E-Way Bill No          : Bill-3290
E-Way Bill Date        : 2026-06-11

Line Items:
Sl.No  Product Name    HSN Code    Qty   Unit      Unit Price   Discount  GST   Amount
Items                                                                           Rs 3,05,190.00
1      Wooden Chair    HSN1234     10    Pieces    Rs 3,500.00  5%        18%   Rs 33,250.00
2      Bookshelf       HSN1235     10    Pieces    Rs 4,200.00  9%        18%   Rs 38,220.00
3      Table Lamp      HSN1236     16    sqmm      Rs 1,500.00  8%        18%   Rs 22,080.00
4      Sofa 3 Seater   HSN1237     13    No's      Rs 18,500.00 12%       18%   Rs 2,11,640.00

Summary:
Total Amount    : Rs 3,05,190.00
CGST 9%         : Rs 27,467.10
SGST 9%         : Rs 27,467.10
Grand Total     : Rs 3,60,124.20
"""
    page.insert_text(
        (50, 50),
        invoice_text,
        fontsize=10,
        fontname="helv",
        color=(0, 0, 0),
    )

    doc.save(output_path)
    doc.close()
    print(f"PDF saved to: {output_path}")


if __name__ == "__main__":
    generate_invoice_pdf("tests/sample_invoice.pdf")
