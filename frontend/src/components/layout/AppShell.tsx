/**
 * AppShell Component (`frontend/src/components/layout/AppShell.tsx`)
 * Implements the 4-Zone Desktop Dashboard (`1280px+`) and Mobile Bottom-Nav
 * Tabbed Workspace (`360px–430px`) with Hebrew RTL (`dir="rtl"`) and English LTR toggle.
 */

import type { FamilyProfile, FlightSearchQuery } from '../../types/domain';

export interface AppShellProps {
  profile: FamilyProfile;
  query: FlightSearchQuery;
  locale: 'he' | 'en';
  activeMobileTab: 'search' | 'calendar' | 'results' | 'profile';
  onToggleLocale: () => void;
  onSelectMobileTab: (tab: 'search' | 'calendar' | 'results' | 'profile') => void;
}

export function renderAppShellHeader(props: AppShellProps): string {
  const isHe = props.locale === 'he';
  const dir = isHe ? 'rtl' : 'ltr';
  const totalPassengers = props.profile.adults_count + props.profile.children.length;
  return `
    <header class="app-header" dir="${dir}">
      <div class="header-brand">
        <span class="brand-badge">✈️ EL AL & MoE</span>
        <h1>${isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner'}</h1>
      </div>
      <div class="header-summary-pills">
        <span class="pill" dir="ltr">${totalPassengers} Pax (${props.profile.adults_count}A + ${props.profile.children.length}C)</span>
        <span class="pill" dir="ltr">${props.profile.matmid_points_balance.toLocaleString()} Matmid</span>
        <button type="button" class="btn-locale-toggle" data-action="toggle-locale">
          ${isHe ? 'EN / LTR' : 'עברית / RTL'}
        </button>
      </div>
    </header>
  `;
}
