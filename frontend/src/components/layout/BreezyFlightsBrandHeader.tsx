/**
 * BreezyFlightsBrandHeader Component (`frontend/src/components/layout/BreezyFlightsBrandHeader.tsx`)
 * Scoped top-of-page Thailand vacation branding for `breezyflights` (`#app-header` & `#vacation-hero` only),
 * featuring the Andaman limestone karst & traditional Thai longtail (`Rua Hang Yao`) motif while keeping
 * below-the-hero tokens and surfaces untouched.
 */

export interface BreezyFlightsBrandHeaderProps {
  locale: 'he' | 'en';
  adultsCount: number;
  childrenCount: number;
  matmidPointsBalance: number;
}

export function renderBreezyFlightsBrandWordmark(locale: 'he' | 'en'): string {
  const isHe = locale === 'he';
  const localTitle = isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner';
  return `
    <div class="header-brand" id="header-brand">
      <h1 id="header-title">
        <span class="brand-wordmark" dir="ltr">breezy<span class="brand-wordmark-accent">flights</span></span>
        <span class="brand-title-sep" aria-hidden="true">·</span>
        <span class="brand-title-local" id="header-title-local">${localTitle}</span>
      </h1>
    </div>
  `;
}
