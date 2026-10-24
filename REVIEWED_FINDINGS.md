# Reviewed findings

## Persistent counter and retry identities

The eight scoped `java:S4790` annotations retain the established MD5-derived
database receipt/counter keys in the feedback, campaign, case, vote, membership,
media-deletion and admin-projection owners. These values are deterministic
identifiers, never credentials, signatures or integrity checks. Authentication,
authorization and signed Registry payloads use separate mechanisms. Changing
these persisted identities would duplicate counter contributions or retry work;
the review preserves their compatibility. This is a reviewed use, not a hash
algorithm upgrade or a repaired cryptographic vulnerability.

## Public header authentication and delegated authorization

The two scoped `java:S4502` annotations cover the canonical header-authenticated
API chain and its delegated receiver. Browser cookies cannot authenticate
protected mutations. The media cookie is limited by `FirebaseFilter` to private
media GET/HEAD requests; even a verified media principal is rejected for unsafe
methods. The receiver obtains authorization for the original method/target and
headers from the verified owner before admitting a request.

Negative checks are in `WebSecurityConfigBootstrapTest`,
`FirebaseFilterPublicDocumentsTest` and `PublicAuthorizationHttpTest` in both
projects. These are reviewed authentication boundaries; CSRF protection was not
removed or relaxed by this change. Cookie/session-based mutation authentication
would require reconsidering these annotations.

## Lab-only addresses, HTTP and container scratch paths

Each Python `NOSONAR` comment identifies its exact reviewed rule and boundary:

| Rule | Reviewed use | Boundary |
| --- | --- | --- |
| `python:S1313` | RFC1918 ranges | Network validation constants, not server addresses. |
| `python:S5332` | Metrics probes and service URLs | The existing private, single-VM lab; service transport already explicitly opts into insecure HTTP. This does not claim TLS protection. |
| `python:S5443` | MinIO marker | A read-only file-existence check inside the owned container. |
| `python:S5443` | Fault-pod scratch mount | A disposable pod's own `emptyDir`, not shared host storage. |

The Mongo seed directory and browser manifests are actual repairs: atomic
private `mktemp` staging replaces predictable directory adoption, and the three
browser tools validate private ownership/permissions, reject symlinks and bound
the existing launcher's manifest before reading its CDP port. Those changes are
separate from the reviewed cases above.

## Internal service CSRF

`java:S4502` reports every `ignoringRequestMatchers` call, including the
authenticated service capability exemption in the internal transport chains.
The method-level suppression in the affected `*ServerConfiguration` classes
records this reviewed case. It does not apply to the public authorization
chain, the canonical browser security configuration or other rules.

The exemption requires all of the following, enforced by the implementation:

- The chain is stateless and accepts only its explicitly bound paths/methods.
- `InternalReadCredentialFilter` verifies exactly one bounded Bearer header
  against the configured service capability and requires a valid REAL/DEMO mode.
- That filter runs before `CsrfFilter`. Only its privately constructed
  `ServiceAuthentication` satisfies `verifiedServiceRequest`.
- Application users and browser cookies cannot acquire that exemption.
- The security and database-mode contexts are restored after success or failure.
- CSRF remains enabled for requests that do not satisfy the verified capability.

`InternalCapabilityChainsTest` constructs every chain in `transport/bindings.json`
and verifies the active CSRF filter, filter order, rejection of ordinary user
authentication and acceptance of a verified service capability. The identity
broker also uses named caller capabilities and is exercised by
`ActorDelegationBrokerHttpTest`. `InternalReadCredentialFilterTest` covers
invalid/duplicate credentials, invalid modes and context restoration.

Removing the blanket CSRF disable and restricting the exemption are code
changes. Resolving the remaining S4502 report on these verified methods is a
reviewed finding, not an additional vulnerability repair. Keep that distinction
when reporting Sonar counts. Do not extend this suppression to a chain that
accepts cookie/session authentication.

## Image converter workspace

The `java:S5443` annotation on `runImageMagickVariant` covers the new, atomically
created private temporary directory. The converter's input and output remain
inside it; the previous shared-directory unlink/reopen race was removed.
`MediaImageConversionTest` checks owner-only directory permissions (`0700`) on
the supported Linux runtime and cleanup after both conversion success and failure.
The residual report on the secure temporary-directory API is a reviewed case,
separate from the file-handling repair.

## Deployment public key permissions

`RegistryNodeIdentityService.PUBLIC_KEY_PERMISSIONS` intentionally permits
reading the public verification key (`0644`). The signing key is `0600`, and
new identity directories are `0700`; symlinks and non-regular key files are
rejected. `RegistryNodeIdentityServiceTest` verifies the distinct key permissions
and unsafe-path rejection. The field-level `java:S2612` annotation applies only
to public verification material, without relaxing private-key permissions.

## STUN executable capability removed

The lab's pinned coturn executable originally carried a file capability, which
prevented exec with an empty capability bounding set. The versioned STUN
Dockerfile makes a byte-identical copy without extended attributes at build time.
It installs no extra runtime tools and retains the same upstream image and STUN
options. The local probe also mounts its scratch filesystems with owner-only
permissions (`0700`, UID/GID 65532), bounded size, and no executable files.
Both lab charts now drop all capabilities without a Sonar exemption;
port 3478 does not require privileged binding. This supersedes the former
NET_BIND_SERVICE exception. The monolith's existing upstream image is separate
from this lab packaging change.

## Frontend compatibility and retained asynchronous work

The main frontend's scoped `S4790` review covers SHA-1 only as the existing
mapping of public demo identities. It does not authenticate users, sign data or
verify integrity. The seed feedback hash's `S7767` annotation retains deliberate
signed 32-bit overflow; replacing it with `Math.trunc` changes persisted IDs.

Both frontends retain two constructor operations under scoped `S7059` comments:
database hydration is stored in `hydrationReady` and awaited through
`whenReady()`, and the notification permission observer handles rejection and
unregisters on destruction. These are reviewed lifetimes. Unhandled application
startup work was separately moved into the existing lifecycle/error handling.

The four main-frontend `S6268` resource URL reviews cover the fixed bundled graph
asset, authenticated HTTP(S)-validated simulator access and waiting URLs, and
the authenticated registration response. Registration now also passes through
the existing `UiLinkUtils.normalizeHttpUrl` before the trust call. Payment frame
messages retain their frame/origin checks. These annotations do not assert that
arbitrary HTML or arbitrary URL schemes are safe.

These narrowly documented cases are reviews, distinct from the actual regex,
randomness, accessibility, lifecycle and duplication repairs. No project-wide
rule disable, source exclusion or duplication exclusion was added for them.
