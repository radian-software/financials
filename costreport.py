#!/usr/bin/env python3

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import sys


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
                return ["Publishing", "Chrome Web Store"]
            if self.description == "AWS" or "Amazon web services" in self.description:
                return ["Web hosting", "Amazon Web Services"]
            if self.description.startswith("AWS: "):
                return [
                    "Web hosting",
                    "Amazon Web Services",
                    self.description.removeprefix("AWS: "),
                ]
            if self.description == "Digitalocean":
                return ["Web hosting", "DigitalOcean"]
            if "COMPANY: FRANTECH" in self.description:
                return ["Web hosting", "Frantech"]
            if "RAILWAY.APP" in self.description or "HTTPSRAILWAY" in self.description:
                return ["Web hosting", "Railway"]
            if "NAME-CHEAP.COM" in self.description:
                return ["Web hosting", "Namecheap"]
            if "LINODE . AKAMAI" in self.description:
                return ["Web hosting", "Linode"]
            if (
                self.description == "California Secretary Of State"
                and self.amount == -20
            ):
                return ["Government", "Document filing", "Statement of Information"]
            if "COMPANY: FRANCHISE TAX BO" in self.description and self.amount == -800:
                return ["Government", "Taxes", "Minimum annual tax"]
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--bluevine-txns", required=True)
    parser.add_argument("--sffire-txns", required=True)
    args = parser.parse_args()
    with open(args.bluevine_txns) as f:
        bluevine_txns = json.load(f)
    with open(args.sffire_txns) as f:
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
    for full_txn in txns:
        if full_txn.should_ignore:
            continue
        for txn in full_txn.split():
            if txn.should_ignore:
                continue
            cur_month = txn.date.year, txn.date.month
            if cur_month != last_month:
                print()
                month_str = txn.date.strftime("%Y %B")
                padding = "=" * (60 - len(month_str))
                if last_notes := notes_dict[last_month]:
                    for note in last_notes:
                        print(note.contents)
                        print()
                print(f"=== {month_str} {padding}")
                print()
                last_month = cur_month
            running_balance += txn.amount
            cat_str = " - ".join(reversed(txn.category))
            print(f"${running_balance:8}    ${txn.amount:7}    {cat_str}")
    if last_notes := notes_dict[last_month]:
        print()
        for note in last_notes:
            print(note.contents)


if __name__ == "__main__":
    main()
    sys.exit(0)
