from celery.schedules import crontab

beat_schedule = {
    # "print-user-count-every-minute": {
    #     "task": "app.celery.tasks.print_user_count",
    #     "schedule": crontab(minute="*/1"),
    # },
    "process-monthly-emi-deductions": {
        "task": "app.celery.tasks.process_monthly_emi_deductions",
        "schedule": crontab(day_of_month="1", hour="0", minute="0"),
    },
    "process-monthly-interest-accrual": {
        "task": "app.celery.tasks.process_monthly_interest_accrual",
        "schedule": crontab(day_of_month="2", hour="0", minute="0"),
    }
    # },
    # "process-monthly-interest-accrual": {
    #     "task": "app.celery.tasks.process_monthly_interest_accrual",
    #     "schedule": crontab(day_of_month="2", hour="0", minute="0"),
    # }
    # "process-monthly-emi-deductions": {
    #     "task": "app.celery.tasks.process_monthly_emi_deductions",
    #     "schedule": crontab(day_of_month="1", hour="0", minute="0"),  # 1st of every month at 00:00 UTC
    # }
}
