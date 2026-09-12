# Documentation deployment

The documentation is published at
[justpen-browser-mcp.justpenkit.justmumu.com](https://justpen-browser-mcp.justpenkit.justmumu.com/)
using the existing Cloudflare Pages Direct Upload project `justpen-browser-mcp`.
The site follows the current `main` branch; it is not a separate archive of each
tagged release. Installation commands continue to use the project version.

## Automatic publication

The `Publish documentation` job in the `CI` workflow runs only for pushes to
`main`, after both complete Python 3.11–3.13 matrices succeed. These include the
quality gates, native browser tests and installed-wheel checks. Pull requests
validate the documentation without deploying or accessing Cloudflare credentials.

The publishing job installs locked dependencies through `make install`, runs
`make docs-build`, and uploads only the resulting `site/` directory. The Pages
deployment records the tested commit and explicitly targets its `main` branch.
The job also checks that Pages reports a production deployment, not a preview.
An older workflow rerun fails before upload if a newer commit is already on main.

Cloudflare's official Wrangler Action runs on the GitHub runner. Contributors
do not need to install Node, npm or Wrangler locally. MkDocs and local development
continue to use Python, uv and Make. Dependabot tracks the Action version through
the existing GitHub Actions update group.

## One-time Cloudflare setup

Use the Cloudflare account containing the Pages project `justpen-browser-mcp`.
The project must use `main` as its production branch. Its custom domain is
`justpen-browser-mcp.justpenkit.justmumu.com`; confirm it is Active with SSL enabled
under **Custom domains**. Add the domain through Pages before managing its DNS
record; a CNAME alone does not register a Pages custom domain.

Find the **Account ID** in the Cloudflare account or zone overview. Create an API
token with **Account → Cloudflare Pages → Edit** permission, restricted to this
account. Store these two values in the repository's **Settings → Secrets and
variables → Actions → New repository secret**:

| Secret                  | Value                                                    |
| ----------------------- | -------------------------------------------------------- |
| `CLOUDFLARE_ACCOUNT_ID` | The account ID containing the Pages project              |
| `CLOUDFLARE_API_TOKEN`  | The token authorized to publish to Pages in that account |

Keep the token in GitHub secrets rather than committing it or putting it in a
command argument. No Cloudflare browser login is needed by the workflow. See
[Cloudflare's Direct Upload CI guide](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)
for the account and token screens.

## Verify and recover

After a merge, open the repository's **Actions → CI** run for the current `main`
commit. A successful `Publish documentation` job confirms the upload; verify the
custom HTTPS domain and a nested page such as
[configuration](../getting-started/configuration.md) before considering the first
deployment complete.

If the publishing job reports missing credentials, add the two repository secrets
and choose **Re-run failed jobs** for that current-main run. The same applies after
correcting an expired token, a wrong account ID, or Pages permission errors.
If Pages reports a preview deployment, set the project's production branch to
`main` before retrying; the preview upload has not published the custom domain.
Direct Upload projects require Cloudflare's
[Update Project API procedure](https://developers.cloudflare.com/pages/get-started/direct-upload/#production-branch-configuration)
for this change; production branch controls are unavailable in the dashboard.
When a newer commit is already on main, use that commit's CI run instead of
republishing an older build. Failed builds or quality gates do not replace the
previously published documentation.

If upload succeeds but the custom domain does not work, inspect the domain's
Pages status and DNS records. Cloudflare provisions the domain's HTTPS certificate;
allow its activation to complete before diagnosing application content.

To preview documentation locally, run `make docs-serve`. To inspect the exact
static output, run `make docs-build` and inspect `site/`; generated files remain
gitignored.
