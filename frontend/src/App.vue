<script setup lang="ts">
import { MarketplaceNotifier, marketplaceNavigation, NotificationBell } from "@realhrsoft/marketplace-employee";
import type { Ref } from "vue";
import { ref } from "vue";

import type { RealHRSoftContext } from "./context";

const props = defineProps<{ context: RealHRSoftContext; companyId: Ref<string | null> }>();
const drawer = ref<boolean | null>(null);
</script>

<template>
  <v-app>
    <v-app-bar flat border>
      <v-app-bar-nav-icon @click="drawer = !drawer" />
      <v-app-bar-title>
        RealHRSoft <span class="text-medium-emphasis text-body-2">(dummy)</span>
      </v-app-bar-title>
      <v-select
        v-model="props.companyId.value"
        :items="props.context.companies"
        :disabled="!props.context.companies.length"
        :placeholder="props.context.companies.length ? 'Choose company' : 'No current employment'"
        item-title="name"
        item-value="id"
        label="Acting for"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 16rem"
        class="mr-2"
      />
      <NotificationBell />
      <v-menu>
        <template #activator="{ props: menu }">
          <v-btn v-bind="menu" icon="mdi-account-circle-outline" aria-label="Account" />
        </template>
        <v-list density="compact">
          <v-list-item :title="props.context.employee" :subtitle="props.context.client ?? 'No client'" />
          <v-divider />
          <v-list-item :href="props.context.urls.home" prepend-icon="mdi-home-outline" title="RealHRSoft home" />
          <form method="post" :action="props.context.urls.logout">
            <input type="hidden" name="csrfmiddlewaretoken" :value="props.context.csrfToken" />
            <v-list-item tag="button" type="submit" prepend-icon="mdi-logout" title="Sign out" class="w-100" />
          </form>
        </v-list>
      </v-menu>
    </v-app-bar>
    <v-navigation-drawer v-model="drawer">
      <v-list nav>
        <v-list-item
          v-for="item in marketplaceNavigation"
          :key="item.title"
          :to="item.to"
          :prepend-icon="item.icon"
          :title="item.title"
          exact
        />
      </v-list>
    </v-navigation-drawer>
    <v-main>
      <v-container style="max-width: 1400px">
        <router-view />
      </v-container>
    </v-main>
    <MarketplaceNotifier />
  </v-app>
</template>
