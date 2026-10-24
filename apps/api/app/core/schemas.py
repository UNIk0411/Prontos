from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RaceStrategyConfig(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')

    strategy_mode: Literal['optimize', 'manual'] = 'optimize'
    race_laps: int = Field(default=57, ge=1, le=500)
    base_lap_time_seconds: float = Field(default=90, gt=30, le=300)
    starting_fuel_kg: float = Field(default=100, gt=0, le=1000)
    fuel_burn_per_lap_kg: float = Field(default=1.7, gt=0, le=10)
    fuel_time_penalty_seconds_per_kg: float = Field(default=0.03, ge=0, le=1)
    pit_loss_seconds: float = Field(default=22, gt=0, le=120)
    tire_wear_seconds_per_lap: float = Field(default=0.06, ge=0, le=5)
    max_stint_laps: int = Field(default=35, ge=1, le=500)
    pit_laps: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def validate_race_constraints(self) -> 'RaceStrategyConfig':
        if self.starting_fuel_kg < self.fuel_burn_per_lap_kg * self.race_laps:
            raise ValueError('Starting fuel must cover the configured race distance')
        if self.strategy_mode == 'manual':
            if self.pit_laps != sorted(set(self.pit_laps)):
                raise ValueError('Pit laps must be unique and in ascending order')
            if any(lap < 1 or lap >= self.race_laps for lap in self.pit_laps):
                raise ValueError('Pit laps must be between lap 1 and the penultimate lap')
            stint_lengths = []
            previous_pit_lap = 0
            for pit_lap in self.pit_laps:
                stint_lengths.append(pit_lap - previous_pit_lap)
                previous_pit_lap = pit_lap
            stint_lengths.append(self.race_laps - previous_pit_lap)
            if any(length > self.max_stint_laps for length in stint_lengths):
                raise ValueError('A planned stint exceeds the maximum stint length')
        elif self.pit_laps:
            raise ValueError('pit_laps can only be supplied in manual strategy mode')
        return self


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='Manually added experiment', max_length=1000)
    category: str = Field(default='CPU-bound numerical workload', min_length=1, max_length=120)
    cpu: float = Field(default=2, gt=0)
    memory: float = Field(default=1, gt=0)
    budget: float = Field(default=10, gt=0)
    priority: int = Field(default=3, ge=1, le=5)
    estimated_runtime: float = Field(default=6, gt=0)
    dependencies: list[str] = Field(default_factory=list)
    deadline: str | None = None
    race_strategy: RaceStrategyConfig | None = None

    @field_validator('name', 'category')
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Value cannot be blank')
        return normalized

    @model_validator(mode='after')
    def validate_race_strategy(self) -> 'ExperimentCreate':
        if self.category == 'Race strategy simulation':
            if self.race_strategy is None:
                self.race_strategy = RaceStrategyConfig()
        elif self.race_strategy is not None:
            raise ValueError('race_strategy settings require the Race strategy simulation category')
        return self

    @field_validator('deadline')
    @classmethod
    def validate_deadline(cls, value: str | None) -> str | None:
        if value is not None:
            from datetime import date

            date.fromisoformat(value)
        return value


class SchedulerRun(BaseModel):
    policy: str = 'adaptive'

    @field_validator('policy')
    @classmethod
    def validate_policy(cls, value: str) -> str:
        allowed = {'fifo', 'priority', 'shortest', 'deadline', 'adaptive'}
        normalized = value.strip().lower()
        if normalized not in allowed:
            raise ValueError(f'Policy must be one of: {", ".join(sorted(allowed))}')
        return normalized


class UserCreate(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=128)
    role: str = 'viewer'

    @field_validator('role')
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {'viewer', 'operator', 'admin'}:
            raise ValueError('Role must be viewer, operator, or admin')
        return value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)

    @model_validator(mode='after')
    def require_update(self) -> 'UserUpdate':
        if not self.model_fields_set:
            raise ValueError('At least one user field must be changed')
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('User fields cannot be null')
        return self

    @field_validator('role')
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in {'viewer', 'operator', 'admin'}:
            raise ValueError('Role must be viewer, operator, or admin')
        return value


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    name: str = Field(min_length=2, max_length=120)
    owner_email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    owner_username: str = Field(min_length=2, max_length=80)
    owner_password: str = Field(min_length=12, max_length=128)
    cpu_quota: float = Field(default=16, gt=0)
    memory_quota: float = Field(default=12, gt=0)
    budget_quota: float = Field(default=1000, gt=0)


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    cpu_quota: float | None = Field(default=None, gt=0)
    memory_quota: float | None = Field(default=None, gt=0)
    budget_quota: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def require_update(self) -> 'OrganizationUpdate':
        if not self.model_fields_set:
            raise ValueError('At least one quota must be updated')
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Quota values cannot be null')
        return self
