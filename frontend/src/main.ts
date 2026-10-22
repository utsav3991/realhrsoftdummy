import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import "@realhrsoft/marketplace-employee/style.css";

import { createMarketplace, marketplaceRoutes } from "@realhrsoft/marketplace-employee";
import { createApp, ref, watch } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { createVuetify } from "vuetify";

import App from "./App.vue";
import { readContext, saveCompany } from "./context";

// RealHRSoft owns the layout, the router, the login and the company switcher; the
// Marketplace screens render inside it under /marketplace.
const context = readContext();
const companyId = ref<string | null>(context.selected);
watch(companyId, (value) => saveCompany(context, value));

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: context.urls.mount, children: marketplaceRoutes() }],
});

createApp(App, { context, companyId })
  .use(createVuetify({ theme: { defaultTheme: "light" } }))
  .use(router)
  .use(
    createMarketplace({
      baseUrl: context.urls.proxy,
      companyId,
      credentials: "same-origin",
      headers: () => ({ "X-CSRFToken": context.csrfToken }),
    }),
  )
  .mount("#app");
