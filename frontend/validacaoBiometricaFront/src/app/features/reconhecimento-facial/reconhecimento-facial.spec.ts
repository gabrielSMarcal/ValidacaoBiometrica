import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReconhecimentoFacial } from './reconhecimento-facial';

describe('ReconhecimentoFacial', () => {
  let component: ReconhecimentoFacial;
  let fixture: ComponentFixture<ReconhecimentoFacial>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReconhecimentoFacial],
    }).compileComponents();

    fixture = TestBed.createComponent(ReconhecimentoFacial);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
