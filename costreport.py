#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import re
import sys


@dataclass
class Transaction:
    serial: int
    account: str
    date: datetime
    amount: Decimal
    description: str

    serial_counter = 0

    @classmethod
    def from_bluevine(cls, txn):
        cls.serial_counter += 1
        return Transaction(
            date=datetime.strptime(txn["date"], "%m/%d/%y"),
            amount=Decimal(txn["amt"].replace(",", "")),
            description=txn["desc"],
            account="BlueVine",
            serial=cls.serial_counter,
        )

    @classmethod
    def from_sffire(cls, txn):
        cls.serial_counter += 1
        return Transaction(
            date=datetime.strptime(txn["date_posted"], "%Y-%m-%dT%H:%M:%S"),
            amount=-Decimal(txn["amount"]),
            description=txn["description"],
            account="SF Fire CU",
            serial=cls.serial_counter,
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
            43,
        }:
            return True
        if "FRANTECH" in self.description and self.serial in {49, 50}:
            return True
        if "Shared branch Deposit" in self.description and self.serial == 47:
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
            if self.description == "Digitalocean":
                return ["Web hosting", "DigitalOcean"]
            if "COMPANY: FRANTECH" in self.description:
                return ["Web hosting", "Frantech"]
            if "RAILWAY.APP" in self.description:
                return ["Web hosting", "Railway"]
            if "NAME-CHEAP.COM" in self.description:
                return ["Web hosting", "Namecheap"]
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
    running_balance = Decimal("0.00")
    last_month = None
    for txn in txns:
        if txn.should_ignore:
            continue
        cur_month = txn.date.year, txn.date.month
        if cur_month != last_month:
            print()
            month_str = txn.date.strftime("%Y %B")
            padding = "=" * (60 - len(month_str))
            print(f"=== {month_str} {padding}")
            print()
            last_month = cur_month
        running_balance += txn.amount
        print(f"${running_balance:8}    ${txn.amount:7}    {txn.category[-1]}")


if __name__ == "__main__":
    main()
    sys.exit(0)
