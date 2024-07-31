#!/usr/bin/env python3

import dotenv

dotenv.load_dotenv()

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys


def datestr(s: str) -> datetime:
    if s.count("-") == 1:
        s += "-01"
    return datetime.strptime(s, "%Y-%m-%d")


@dataclass
class Note:
    contents: str
    date: datetime


@dataclass
class Transaction:
    serial: Decimal
    account: str
    date: datetime
    amount: Decimal
    description: str

    serial_counter = 0

    @classmethod
    def from_bluevine(cls, txn):
        cls.serial_counter += 1
        return Transaction(
            date=datetime.strptime(txn["date"].removeprefix("\x0c"), "%m/%d/%y"),
            amount=Decimal(txn["amt"].replace(",", "")),
            description=txn["desc"],
            account="BlueVine",
            serial=Decimal(cls.serial_counter),
        )

    @classmethod
    def from_sffire(cls, txn):
        cls.serial_counter += 1
        return Transaction(
            date=datetime.strptime(txn["date_posted"], "%Y-%m-%dT%H:%M:%S"),
            amount=-Decimal(txn["amount"]),
            description=txn["description"],
            account="SF Fire CU",
            serial=Decimal(cls.serial_counter),
        )

    @property
    def should_ignore(self) -> bool:
        if re.search(r"COMPANY: ELEVATIONS ?CU ENTRY: ACCTVERIFY", self.description):
            return True
        if "SF Fire CU, ACCTVERIFY" in self.description:
            return True
        if "PAYPAL, VERIFYBANK" in self.description:
            return True
        if self.description in {"Outbound Check", "Check Deposit"} and self.serial in {
            37,
            48,
        }:
            return True
        if abs(self.amount) == Decimal("389.49") and self.serial in {45, 52}:
            return True
        if "FRANTECH" in self.description and self.serial in {54, 55}:
            return True
        return False

    @property
    def category(self) -> list[str]:
        if self.amount < 0:
            if "ACH payment to Radon" in self.description and self.serial == 8:
                return ["Intellectual property"]
            if self.description == "Outbound Check" and self.serial == 38:
                return ["Business operations", "Banking", "Account opening"]
            if "Temporary Checks" in self.description:
                return ["Business operations", "Banking", "Temporary checks"]
            if "fastmail pty ltd" in self.description.lower():
                return ["Business operations", "Email", "Fastmail"]
            if re.search(r"(GOOGLE|Google LLC)[* ]GSUITE", self.description):
                return ["Business operations", "Email", "Google Workspace"]
            if "USPS CHANGE OF ADDRESS" in self.description:
                return ["Business operations", "Postal service", "Change of address"]
            if "POS Card purchase USPS PO" in self.description:
                return ["Business operations", "Postal service", "Postage"]
            if "CRYPTPAD-PERSONAL" in self.description:
                return ["Business operations", "Document hosting", "CryptPad"]
            if "PIKAPODS.COM" in self.description:
                return ["Business operations", "Document hosting", "PikaPods"]
            if "FATHOM ANALYTICS" in self.description:
                return ["Analytics", "Fathom Analytics"]
            if "GOOGLE *Chrome" in self.description:
                cat = ["Publishing", "Chrome Web Store"]
                if self.date.year == 2022:
                    cat.append("Hypercast")
                return cat
            if self.description == "AWS" or "Amazon web services" in self.description:
                return ["Web hosting", "Amazon Web Services"]
            if self.description.startswith("AWS: "):
                return [
                    "Web hosting",
                    "Amazon Web Services",
                    self.description.removeprefix("AWS: "),
                ]
            if self.description == "Digitalocean":
                cat = ["Web hosting", "DigitalOcean"]
                if self.date < datestr("2024-01"):
                    cat.append("Riju")
                return cat
            if "COMPANY: FRANTECH" in self.description:
                cat = ["Web hosting", "Frantech"]
                if self.date < datestr("2024-01"):
                    if self.amount == Decimal("-7.70"):
                        cat.append("dontbeevilmirror")
                    else:
                        cat.append("Riju")
                return cat
            if "RAILWAY.APP" in self.description or "HTTPSRAILWAY" in self.description:
                return ["Web hosting", "Railway"]
            if "NAME-CHEAP.COM" in self.description:
                return ["Web hosting", "Namecheap"]
            if "LINODE . AKAMAI" in self.description:
                cat = ["Web hosting", "Linode"]
                if self.date < datestr("2024-04"):
                    cat.append("Dominion Wiki")
                return cat
            if (
                self.description == "California Secretary Of State"
                and self.amount == -20
            ):
                return ["Government", "Document filing", "Statement of Information"]
            if "COMPANY: FRANCHISE TAX BO" in self.description and self.amount == -800:
                return ["Government", "Taxes", "Minimum annual tax"]
            if (
                "COMPANY: FRANCHISE TAX BO" in self.description
                and self.amount == Decimal("-22.25")
            ):
                return ["Government", "Taxes", "California FTB fine"]
            if (
                "COMPANY: FRANCHISE TAX BO" in self.description
                and self.amount == Decimal("-881.41")
            ):
                return ["Government", "Taxes", "California FTB fine"]
        if self.amount > 0:
            if "Interest earned" in self.description:
                return ["Business operations", "Banking", "Bank account interest"]
            if (
                re.search(r"COMPANY: ELEV(ATIONS)? ?CU", self.description)
                or "Transfer from Elevations" in self.description
            ) and self.amount > 500:
                return ["Capital contribution"]
            if (
                "COMPANY: GITHUB SPONSORS" in self.description
                or self.description == "GitHub Sponsors, GitHub Spo"
            ):
                return ["Revenue", "Donations", "GitHub Sponsors"]
            if "COMPANY: STRIPE" in self.description:
                return ["Revenue", "Donations", "Ko-Fi"]
        raise RuntimeError(f"Uncategorized transaction: {self}")

    def split(self):
        if self.category[-1] == "Amazon Web Services":
            billable_month = (self.date - timedelta(days=15)).strftime("%Y-%m")
            if billable_month == "2022-04":
                return [
                    Transaction(
                        date=self.date,
                        amount=self.amount,
                        description="AWS: Tinyku",
                        account=self.account,
                        serial=Decimal(self.serial) + Decimal("0.1"),
                    )
                ]
            with open(f"aws-by-month/{billable_month}/breakdown.txt") as f:
                txns = []
                remaining_amount = -self.amount
                idx = 0
                biggest_idx = 0
                biggest_amt = 0
                for line in f:
                    if match := re.match(r"([^ ]+) :: \$([0-9.]+)", line):
                        project = match.group(1)
                        amount = Decimal(match.group(2))
                        txns.append(
                            Transaction(
                                date=self.date,
                                amount=-amount,
                                description=f"AWS: {project}",
                                account=self.account,
                                serial=Decimal(self.serial)
                                + Decimal("0.1") * (idx + 1),
                            )
                        )
                        if amount > biggest_amt:
                            biggest_idx = idx
                            biggest_amt = amount
                        idx += 1
                        remaining_amount -= amount
                assert abs(remaining_amount) < 0.05, remaining_amount
                if remaining_amount != 0:
                    txns[biggest_idx].amount -= remaining_amount
                return txns
        return [self]


# There turn out not to be any AWS notes to read, but I already wrote
# the code so :P
def read_aws_notes() -> list[Note]:
    notes = []
    for entry in Path("aws-by-month").iterdir():
        breakdown = entry / "breakdown.txt"
        if not breakdown.is_file():
            continue
        month = datetime.strptime(entry.name, "%Y-%m")
        with open(breakdown) as f:
            text = f.read()
        _, *extra = text.split("\n\n", maxsplit=1)
        if not extra:
            continue
        notes.append(Note(contents=extra[0].strip(), date=month))
    return notes


def read_extra_notes() -> list[Note]:
    notes = []
    for entry in Path("annotations").iterdir():
        month = datetime.strptime(entry.name, "%Y-%m.txt")
        with open(entry) as f:
            text = f.read().strip()
        notes.append(Note(contents=text, date=month))
    return notes


def main():
    with open(os.environ["BLUEVINE_TXNS"]) as f:
        bluevine_txns = json.load(f)
    with open(os.environ["SFFIRE_TXNS"]) as f:
        sffire_txns = json.load(f)["txns"]
    txns: list[Transaction] = []
    txns.extend(map(Transaction.from_bluevine, bluevine_txns))
    txns.extend(map(Transaction.from_sffire, sffire_txns))
    txns.sort(key=lambda txn: txn.date)
    notes: list[Note] = []
    notes.extend(read_aws_notes())
    notes.extend(read_extra_notes())
    notes_dict = defaultdict(list)
    for note in notes:
        notes_dict[note.date.year, note.date.month].append(note)
    running_balance = Decimal("0.00")
    last_month = None
    lines = []

    def put(line):
        print(line)
        lines.append(line)

    split_txns = []
    for full_txn in txns:
        if full_txn.should_ignore:
            continue
        for txn in full_txn.split():
            if txn.should_ignore:
                continue
            split_txns.append(txn)
            cur_month = txn.date.year, txn.date.month
            if cur_month != last_month:
                put("")
                month_str = txn.date.strftime("%Y %B")
                padding = "=" * (60 - len(month_str))
                if last_notes := notes_dict[last_month]:
                    for note in last_notes:
                        put(note.contents)
                        put("")
                put(f"=== {month_str} {padding}")
                put("")
                last_month = cur_month
            running_balance += txn.amount
            cat_str = " - ".join(txn.category)
            put(f"${running_balance:8}    ${txn.amount:7}    {cat_str}")
    if last_notes := notes_dict[last_month]:
        put("")
        for note in last_notes:
            put(note.contents)
    with open("ledger.txt", "w") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print()
    lines = []
    put("=== Spending and revenue category totals ========================")
    put("")
    put("    [ sorted by category ]")
    put("")
    all_cats = set()
    for txn in split_txns:
        all_cats.add(tuple(txn.category))
    subtotals = {}
    for cat in sorted(all_cats):
        subtotal = sum(txn.amount for txn in split_txns if txn.category == list(cat))
        subtotals[cat] = subtotal
        cat_str = " - ".join(cat)
        put(f"${subtotal:8}    {cat_str}")
    put("")
    put("    [ sorted by amount ]")
    put("")
    for cat in sorted(all_cats, key=lambda cat: subtotals[cat]):
        subtotal = subtotals[cat]
        cat_str = " - ".join(cat)
        put(f"${subtotal:8}    {cat_str}")
    with open("categories.txt", "w") as f:
        f.write("\n".join(lines))
        f.write("\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
