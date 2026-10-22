/**
 * What the Django page tells the app about the signed-in employee (json_script
 * `realhrsoft-context`, built in portal/views.py). The browser never sees a Marketplace
 * token: calls go to Django's proxy, which signs one per request.
 */
export interface Company {
  id: string;
  name: string;
}

export interface RealHRSoftContext {
  employee: string;
  client: string | null;
  companies: Company[];
  selected: string | null;
  csrfToken: string;
  urls: { home: string; logout: string; selectCompany: string; proxy: string; mount: string };
}

export function readContext(): RealHRSoftContext {
  const element = document.getElementById("realhrsoft-context");
  if (!element?.textContent) throw new Error("Missing realhrsoft-context");
  return JSON.parse(element.textContent) as RealHRSoftContext;
}

/** Remember the company in the RealHRSoft session, so every page agrees on it. */
export async function saveCompany(context: RealHRSoftContext, companyId: string | null) {
  const body = new URLSearchParams({ company: companyId ?? "" });
  await fetch(context.urls.selectCompany, {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: { Accept: "application/json", "X-CSRFToken": context.csrfToken },
  });
}
