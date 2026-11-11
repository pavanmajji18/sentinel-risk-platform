<!-- Written by Euron Code after each task. It is rewritten automatically: put your own rules in
     another file in .euron/rules/. -->

# Learned in this project


## Security (from .euron/security/assessment.md)
- This code base has had: weak hash (md5/sha-1) (SEC060). Use SHA-256 for integrity and bcrypt/argon2/scrypt for passwords. Do not add more; fix the existing ones when you touch those files.
