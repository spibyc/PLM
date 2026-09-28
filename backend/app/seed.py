"""Sample development data, created through the same services as the UI (fully audited)."""
from sqlalchemy import select

from app.db import new_session
from app.models import User
from app.services import auth, inventory, items, locations

USERS = [
    ("admin", "Alex Admin", "ADMIN"), ("eng1", "Erin Engineer", "ENGINEERING"),
    ("eng2", "Evan Engineer", "ENGINEERING"), ("qa1", "Quinn Quality", "QUALITY"),
    ("prod1", "Pat Production", "PRODUCTION"), ("buyer1", "Bailey Buyer", "PURCHASING"),
]

PARTS = [
    ("RES 10k 0603 1% 0.1W", "Passive", "Resistor", "Resistor", "10k", "0603", "Yageo", "RC0603FR-0710KL",
     "Vishay", "CRCW060310K0FKEA", 500),
    ("CAP 100nF 0603 50V X7R", "Passive", "Capacitor", "Capacitor", "100nF", "0603", "Murata", "GRM188R71H104KA93D",
     "Samsung", "CL10B104KB8NNNC", 1000),
    ("IC MCU ARM Cortex-M4 LQFP-64", "Semiconductor", "Microcontroller", "IC", "STM32F4", "LQFP-64",
     "STMicroelectronics", "STM32F405RGT6", None, None, 20),
    ("IC LDO 3.3V 500mA SOT-223", "Semiconductor", "Regulator", "IC", "3.3V", "SOT-223", "Diodes Inc",
     "AP1117E33G-13", "Texas Instruments", "LM1117MPX-3.3/NOPB", 50),
]


def seed(password: str) -> None:
    with new_session() as db:
        auth.bootstrap_roles(db)
        from app.services.cli_actor import cli_actor

        sysact = cli_actor()
        users = {}
        for un, name, role in USERS:
            u = db.execute(select(User).where(User.username == un)).scalar_one_or_none()
            if u is None:
                u = auth.create_user(db, sysact, un, name, None, password, [role])
            users[un] = auth.actor_for(db, u)
        db.commit()

        eng, eng2, qa, prod = users["eng1"], users["eng2"], users["qa1"], users["prod1"]
        admin = users["admin"]
        site = locations.create_location(db, admin, None, "site", "LAB", "Main Site", False, None)
        room = locations.create_location(db, admin, site.id, "room", "STORES", "Component Stores", False, None)
        cab = locations.create_location(db, admin, room.id, "cabinet", "C01", "Cabinet 1", False, None)
        bins = [locations.create_location(db, admin, locations.create_location(
            db, admin, cab.id, "drawer", f"D0{d}", f"Drawer {d}", False, None).id, "bin", "B01", "Bin 1", False, None)
            for d in (1, 2)]
        qroom = locations.create_location(db, admin, site.id, "room", "QUAR", "Quarantine Cage", True, None)
        prodloc = locations.create_location(db, admin, site.id, "room", "PROD", "Production Line", False, None)
        db.commit()

        for i, (desc, cat, sub, ctype, val, pkg, m1, mpn1, m2, mpn2, qty) in enumerate(PARTS):
            item = items.create_item(db, eng, "component", "pcs", {
                "description": desc, "category": cat, "subcategory": sub, "component_type": ctype, "value": val,
                "package": pkg, "rohs_status": "Compliant", "reach_status": "Compliant"}, min_stock=qty // 2)
            rev = db.execute(select(items.ItemRevision).where(items.ItemRevision.item_id == item.id)).scalar_one()
            items.submit(db, eng, item.id, rev.id)
            items.sign(db, eng2, item.id, rev.id, "Engineering Approved", password, "Reviewed against datasheet", None)
            items.sign(db, qa, item.id, rev.id, "Quality Approved", password, None, None)
            items.sign(db, qa, item.id, rev.id, "Released for Production", password, None, None)
            e1 = items.add_aml(db, eng, item.id, m1, mpn1, True, None, lifecycle="Active")
            items.sign_aml(db, qa, item.id, e1.id, "AML Approved", password, None)
            if m2:
                e2 = items.add_aml(db, eng, item.id, m2, mpn2, False, "Second source", lifecycle="Active")
                items.sign_aml(db, qa, item.id, e2.id, "AML Approved", password, None)
            db.commit()
            if i < 3:
                lot = inventory.receive(db, prod, item_id=item.id, qty=qty * 2, location_id=bins[i % 2].id,
                                        manufacturer_part_id=e1.manufacturer_part_id, supplier_name="Farnell",
                                        purchase_order_ref=f"PO-DEMO-{i + 1:03d}", supplier_lot=f"SL{1000 + i}",
                                        date_code="2542")
                inventory.inspect(db, qa, lot.id, True, password, "Visual inspection and CoC checked")
                db.commit()
        # A draft part awaiting review, and a quarantined lot
        items.create_item(db, eng, "component", "pcs", {"description": "LED Green 0603 20mA", "category": "Opto",
                                                        "value": "Green", "package": "0603"})
        lot_id = db.execute(select(inventory.InventoryLot.id).order_by(inventory.InventoryLot.lot_no)).scalars().first()
        inventory.quarantine(db, qa, lot_id, "NCR-DEMO-001", "Suspected moisture damage")
        inventory.transfer(db, prod, lot_id, bins[0].id, qroom.id, 100, "Moved to quarantine cage")
        db.commit()
        _ = prodloc
