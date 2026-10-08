import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RestrictedDashboard } from './restricted-dashboard';

describe('RestrictedDashboard', () => {
  let component: RestrictedDashboard;
  let fixture: ComponentFixture<RestrictedDashboard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RestrictedDashboard],
    }).compileComponents();

    fixture = TestBed.createComponent(RestrictedDashboard);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
