import { Component } from '@angular/core';
import { inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { MockAuthService } from '../../core/services/mock-auth.service';

@Component({
  imports: [RouterLink],
  selector: 'app-reconhecimento-facial',
  styleUrl: './reconhecimento-facial.css',
  templateUrl: './reconhecimento-facial.html',
})
export class ReconhecimentoFacial {
  protected readonly auth = inject(MockAuthService);
  private readonly router = inject(Router);

  confirmarReconhecimento(): void {
    void this.router.navigateByUrl('/restricted-dashboard');
  }
}
