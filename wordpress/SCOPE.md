# WordPress — SCOPE

> Program handle: `wordpress`
> Synchronized directly via HackerOne API.
> Har hunting session se pehle scope verify karein. Sirf in-scope targets par testing karein.

## Program Info
- **Handle:** `wordpress`
- **Name:** WordPress
- **Bounty Eligible:** True

## In-Scope Assets (Eligible for Bounty)
| Asset Identifier | Type | Scope ID | Max Severity |
|---|---|---|---|
| `WordPress Core` | source_code | 2750 | critical |
| `BuddyPress Core` | source_code | 2751 | critical |
| `bbPress Core` | source_code | 2752 | critical |
| `*.wordpress.org` | wildcard | 2753 | critical |
| `api.wordpress.org` | url | 2754 | critical |
| `*.buddypress.org,bbpress.org,profiles.wordpress.org` | wildcard | 2755 | critical |
| `*.wordcamp.org` | wildcard | 2756 | critical |
| `codex.wordpress.org,codex.bbpress.org,codex.buddypress.org` | url | 2757 | medium |
| `mercantile.wordpress.org` | url | 2758 | medium |
| `*.trac.wordpress.org, *.svn.wordpress.org, *.git.wordpress.org, github.com/WordPress` | source_code | 2759 | critical |
| `planet.wordpress.org` | url | 2762 | critical |
| `*.wordpress.net` | wildcard | 2763 | low |
| `Gutenberg` | source_code | 5545 | critical |
| `GlotPress` | source_code | 17141 | critical |
| `WP-CLI` | source_code | 17142 | critical |
| `Official WordPress plugins` | source_code | 17143 | critical |
| `wordpressfoundation.org` | url | 17572 | medium |
| `doaction.org` | url | 37306 | critical |

## Excluded / Out-of-Scope
*(Strictly do NOT touch any of these)*
- `irclogs.wordpress.org`
- `lists.wordpress.org`
- `*.wordpress.com`
- `status.wordpress.org,glotpress.blog,wordpress.tv`
- `335703880`
- `org.wordpress.android`
- `munin-*.wordpress.org`
- `Digital Ocean, AWS, etc`
- `Archived GitHub repositories`

## Program Policy Excerpt
[WordPress](https://wordpress.org/) is an open-source publishing platform. Our HackerOne program covers the Core software, as well as a variety of related projects and infrastructure.

Our most critical targets are:

* WordPress Core [software](https://wordpress.org/download/source/).
* WordPress.org [API](https://codex.wordpress.org/WordPress.org_API) and [website](https://wordpress.org/).
* Gutenberg [software](https://github.com/WordPress/gutenberg/).
* WP-CLI [software](https://github.com/wp-cli/) and [website](https://wp-cli.org/).
* BuddyPress [software](https://buddypress.org/download/) and [website](https://buddypress.org/).
* bbPress [software](https://bbpress.org/download/) and [website](https://bbpress.org/).
* WordCamp.org [website](https://central.wordcamp.org).
* Supply chain and CI/CD workflows for the above.

Source code for most websites can be found in [our GitHub account](https://github.com/WordPress/), or in the Meta repository (`git clone git://meta.git.wordpress.org/`). Many of the sites have Docker environments that will automatically provision a local copy for you to test against.

**All bounties are doubled** [if they're reported before the bug is released to users](https://make.wordpress.org/security/2019/02/13/doubling-bounties-for-vulnerabilities-discovered-before-release/).

*Please note that __WordPress.com is a separate entity__ from the main WordPress open source project. Please report vulnerabilities for WordPress.com or the WordPress iOS and Android mobile apps through [Automattic's HackerOne page](https://hackerone.com/automattic).*

## Qualifying Vulnerabilities

Any reproducible vulnerability that has a severe effect on the security or privacy of our users is likely to be in scope for the program. Common examples include XSS, CSRF, SSRF, RCE, SQLi, and privilege escalation.

We generally **aren’t** interested in the following problems:

* Issues on `wordpress.org` are in scope only if they can be exploited using the default user ...
