import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-dashboard',
  styleUrl: './restricted-dashboard.css',
  templateUrl: './restricted-dashboard.html',
})
export class RestrictedDashboard implements OnInit {
  protected readonly auth = inject(AuthService);

  ngOnInit(): void {
    if (!this.auth.currentUser()) {
      this.auth.carregarSessao().pipe(
        catchError(() => EMPTY),
      ).subscribe();
    }
  }
}
