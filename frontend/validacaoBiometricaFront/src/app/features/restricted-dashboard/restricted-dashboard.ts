import { Component } from '@angular/core';
import { inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { MockAuthService } from '../../core/services/mock-auth.service';

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-dashboard',
  styleUrl: './restricted-dashboard.css',
  templateUrl: './restricted-dashboard.html',
})
export class RestrictedDashboard {
  protected readonly auth = inject(MockAuthService);
}
