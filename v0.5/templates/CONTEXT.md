# CONTEXT.md — {project name}

> The domain glossary for this project. Domain terms only — no implementation jargon. Used in variable names, file names, test descriptions, commit messages.
>
> One definition per term. No synonyms. If two words mean the same thing, pick one and delete the other.

---

## How to use this file

- **Read it before any domain work.** Both humans and agents must use only terms defined here when discussing or writing domain code.
- **Add a new entry the first time a new term is needed**, before writing any code that uses it.
- **One definition per term.** No synonyms.
- **Order: alphabetical within section.**

## Entry template

```markdown
### {term}

**Definition.** {One or two sentences. Specific, not generic.}

**Related.** {Other CONTEXT.md terms it interacts with.}

**Not the same as.** {Other terms it's sometimes confused with, and why they're different.}
```

---

## Terms

### {term-a}

**Definition.** {…}

**Related.** {…}

**Not the same as.** {…}

### {term-b}

**Definition.** {…}

---

## Open questions

Anything domain-uncertain that the user hasn't yet answered. Mark explicitly — don't bury inline.

- [ ] {Question}
- [ ] {Question}

---

## Out of scope

Terms or concepts the project deliberately does not use, with the reason.

- {term-x} — {why we don't use it}
