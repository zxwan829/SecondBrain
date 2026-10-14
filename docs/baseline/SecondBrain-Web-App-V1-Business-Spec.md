---
version: 1.0
status: canonical
type: business-spec
product: SecondBrain Web App / Personal OS
---

# SecondBrain Web App / Personal OS V1 Business Specification

## 1. Product definition

SecondBrain Web App / Personal OS is the user-facing web entry point for daily SecondBrain use. It is not a Hermes administration-console skin, a single dashboard, a file manager, or a traditional enterprise back office.

The product is a **Global App Shell + extensible left navigation + multiple business pages + dynamic Home**. The video reference defines the visual direction for Home / Overview only; it does not prescribe one layout for every page.

## 2. Global App Shell

All pages share a stable shell: left navigation, top status, main content area, global search and shortcuts, notifications/pending state, visual system, authentication, and routing. Business pages may use their own appropriate layouts.

## 3. Home / Overview

Home is the dynamic AI workspace: futuristic but readable, central visual focus, status animation, layered cards, micro-interactions, subtle glow, and living interface. It aggregates Today, Calendar, pending Review, Agent status, recent Capture, project next actions, Daily Brief, recent Knowledge, personal events, and reading progress as available. Home is not a data source of truth; it consumes formal module data.

## 4. V1 navigation and modules

V1 navigation includes Home, Chat, Today/Calendar, Inbox, Review, Projects, Knowledge, Daily Brief, and Activity. Agent Health may live on Home or in a secondary system area. Provider, MCP, model, and tool configuration remain outside primary business navigation.

- **Chat:** SecondBrain-owned Chat UI using Hermes chat/session APIs; continue sessions, show agent/tool state, and later support attachment/capture. Users need not enter Hermes Dashboard.
- **Today/Calendar:** personal timeline for schedule, todo, journal, birthdays, anniversaries, reminders, project milestones, and personal events. V1 may be read-only/partial and must not broaden Journal write permissions.
- **Inbox:** read-first view of 00-Inbox with source, type, created time, and status.
- **Review/Approval:** 10-Review, Skill pending, Human Approval items, and Promote candidates; preserve WAITING FOR ME semantics and approval boundaries.
- **Projects:** active projects, status, recent activity, next action, and related notes without exposing a raw file tree as the main UI.
- **Knowledge:** recent knowledge, search, tags, type, date, and related project; no complex graph in V1.
- **Daily Brief:** latest brief, summaries, categories, and history.
- **Activity:** user-understandable Capture, Review, Promote, Agent, Skill, and project activity, not a raw debug log.

## 5. Extensibility contracts

Navigation must use a NAV MODULE REGISTRY or equivalent. A module can declare `id`, `route`, `title`, `icon`, `order`, `visibility`, `badge_source`, `home_widgets`, and `permissions`.

A Page Module Contract provides route, page component, data source, read/write capability, permissions, Home widget/card, Activity event source, and optional Calendar event source. Home is an aggregation layer accepting cards, counters, alerts, next actions, recent items, progress, and event notices from modules. Calendar accepts Journal, Todo, Projects, People birthdays, Personal Events, reading plans, and reminders as future sources; it must not be limited to Journal.

## 6. Reserved future modules

Books, People, Personal Events, Travel, Collections, Finance, Health, Media, Reading, and Learning are reserved extension examples. Books may include files, metadata, reading status, chapters, notes, highlights, summaries, quotes, conversations, and relations. People may include relationships, birthdays, important dates, notes, journal/events, and reminders. Personal Events include birthdays, anniversaries, recurring reminders, and events from People. These are not V1 implementations, but V1 architecture must allow registration without refactoring the shell.

## 7. Design and interaction

Global visual language: clean, modern, AI-native, subtly futuristic, consistent spacing and typography, reusable cards, and future-compatible dark/light themes. Home may be highly dynamic; content pages should optimize reading and operation. Default interaction principles are ZERO LEARNING COST, LOW FRICTION, and NATURAL LANGUAGE FIRST. High-frequency actions should take one or two clicks. Desktop has the full shell, iPad a full or compressed sidebar, and Mobile prioritizes Home, Chat, Today, Review, and Inbox.

## 8. Data, runtime, and security boundaries

SecondBrain files remain the business Source of Truth; no second formal knowledge database. Target: SecondBrain-owned React/TypeScript Web App (including Chat UI) served by SecondBrain App/Core; browser uses one App origin, while server-side adapters use supported Hermes Agent/Chat/Session/Skill APIs. Existing FE-4 UI is a migration baseline, not a Hermes Dashboard dependency. Do not reimplement Agent Runtime, session engine, Skill manager, Provider manager, MCP manager, or model routing. V1 must function on LAN HTTP and pass complete business regression through a trusted HTTPS reverse proxy without opening public access.

Default security is LAN-only with authentication, Private exclusion, least privilege, controlled writes, Human Approval, no implicit Promote, and no automatic permission expansion. Future People data requires a separately defined privacy scope and is not read by V1.

## 9. Scope

**V1 MUST:** Global App Shell, extensible navigation, Home, Chat, Today/Calendar, Inbox, Review/Approval, Projects, Knowledge, Daily Brief, Activity, auth, responsive layout, dynamic Home system, module architecture, Home and Calendar aggregation, Human Approval boundary, and Private exclusion.

**V1 SHOULD:** Quick Capture, Journal quick entry, badges, notifications, session continuation, keyboard shortcuts, contextual actions, and Agent status animation.

**V1 DEFERRED:** Books, People, Personal Events management, Finance, Travel, Health, complex knowledge graph, heavy 3D, public internet exposure, full admin-console replacement, and native mobile app.

## 10. Acceptance criteria

V1 is complete only when Home has a clear dynamic AI workspace, the shell and navigation work, Chat is usable, Today/Calendar, Inbox, Review, Projects, Knowledge, Daily Brief, and Activity show real data, approval and Private boundaries remain intact, Desktop/iPad/Mobile are basically usable, and adding a mock future module requires no shell refactor while supporting route/navigation/Home-widget registration.

## 11. Status reference

Phase sequencing, implementation state, and remaining acceptance work are tracked in `00-CURRENT.md` and `Progress-Log.md`; this Business Specification defines the product contract, not a live project status feed.
