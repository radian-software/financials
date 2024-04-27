The BlueVine transactions JSON file came from running these shell
commands on all my BlueVine statement PDFs:

```
% for pdf in *.pdf; do pdftotext -layout $pdf; done
% for f in *.txt; do cat $f | grep -A9999 Transactions | grep -B9999 'In case of errors' | grep / | sed -E 's|([^ ]+) +(.+?) +\$([^$]+)$|\1\t\2\t\3|' | jq -R 'split("\t") | {date: .[0], desc: (.[1] | sub(" *$";"")), amt: .[2]}' | jq -s > ${f/.txt/.json}; done
% cat *.json | jq -s flatten
```

The SF Fire transactions JSON file is from `regex_accountant`
(personal finance manager, not yet released) using Plaid to pull
transactions history.
