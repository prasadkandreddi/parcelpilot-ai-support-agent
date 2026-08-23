# 🚚 ParcelPilot AI Support Agent

An AI-powered customer support and operations assistant for ParcelPilot, a B2B logistics platform.

The system combines Generative AI, RAG, document retrieval, structured operational data, access control, and human confirmation to provide reliable and auditable support responses.

---

## 🎯 Problem

ParcelPilot's support team handles questions related to:

- Customer accounts
- Customer-specific agreements
- Shipment cancellations
- Service credits
- Support SLAs
- Orders
- Support tickets
- Product issues

The information is spread across policies, customer agreements, SOPs, product documentation, historical tickets, and structured operational data.

Some documents may be outdated, customer agreements may override general policies, and historical ticket resolutions may contain incorrect information.

This project provides an AI support assistant that retrieves relevant information, checks the correct sources, protects customer data, and escalates cases when human judgment is required.

---

## ✨ Features

### 🤖 AI Customer Support Chatbot

The chatbot accepts natural-language support questions.

Example:

> Can Northstar cancel ORD-1001 without a cancellation fee? Explain why.

The agent can investigate the order, customer agreement, and applicable policies before generating an answer.

---

### 🔎 Hybrid RAG

The system searches the supplied ParcelPilot documents using hybrid retrieval.

It can retrieve:

- Support policies
- Customer agreements
- Cancellation and service-credit SOPs
- Product documentation
- Known issues

The retrieval layer combines semantic and keyword-based search.

---

### 📊 Structured Data Lookup

The agent can query operational data containing:

- Accounts
- Orders
- Tickets

This allows the system to answer questions using actual operational records.

---

### 🧮 Calculation Tool

A deterministic calculation tool is available for:

- SLA calculations
- Time differences
- Durations
- Numerical calculations
- Service-related calculations

---

### 🚨 Escalation Tool

When a request requires human judgment or cannot be safely resolved, the agent can prepare an escalation.

State-changing actions are not executed automatically.

The user must explicitly confirm the action before it is executed.

---

### 🔐 Access Control

Customer data is scoped to the user's account.

A customer can only access information belonging to their own account.

Access control is enforced in the data/tool layer rather than relying only on the LLM prompt.

---

### 📚 Source Reliability

The system uses source priority when resolving conflicts.

Priority order:

1. Applicable current customer agreement
2. Current support policy
3. Current SOP
4. Current product documentation
5. Other current documentation
6. Deprecated documentation
7. Historical ticket resolutions

Historical ticket resolutions are treated as contextual evidence because they may contain incorrect guidance.

---

### 📈 Operations Intelligence

The internal operations view helps identify:

- SLA-risk tickets
- Recurring issues
- High-priority support activity
- Issues affecting multiple customers
- Unusual support patterns

This helps the support team move from reactive support toward proactive issue detection.

---

# 🏗️ Architecture

```text
                         ┌──────────────────────┐
                         │    Streamlit UI      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Gemini AI Agent    │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
      │ Document     │      │ Structured   │      │ Calculator   │
      │ Search       │      │ Data Lookup  │      │ Tool         │
      └──────┬───────┘      └──────┬───────┘      └──────────────┘
             │                     │
             ▼                     ▼
      ┌──────────────┐      ┌──────────────┐
      │ Policies     │      │ Accounts     │
      │ Agreements   │      │ Orders       │
      │ SOPs         │      │ Tickets      │
      │ Product Docs │      │              │
      └──────────────┘      └──────────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │   Escalation    │
                           │ Confirmation    │
                           └─────────────────┘
