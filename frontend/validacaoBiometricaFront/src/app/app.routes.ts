import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./features/home/home').then((m) => m.Home)
  },
  {
    path: 'login',
    loadComponent: () => import('./features/login-page/login-page').then((m) => m.LoginPage)
  },
  {
    path: 'restricted-dashboard',
    loadComponent: () =>
      import('./features/restricted-dashboard/restricted-dashboard').then((m) => m.RestrictedDashboard)
  },
  {
    path: 'reconhecimento-facial',
    loadComponent: () =>
      import('./features/reconhecimento-facial/reconhecimento-facial').then((m) => m.ReconhecimentoFacial)
  },
  {
    path: 'painel-admin',
    loadComponent: () => import('./features/painel-admin/painel-admin').then((m) => m.PainelAdmin)
  },
  {
    path: '**',
    redirectTo: ''
  }
];
