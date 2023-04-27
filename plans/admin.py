# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import CirclePlan


@admin.register(CirclePlan)
class CirclePlanAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'description',
        'content',
        'date_created',
        'created_by',
    )
    list_filter = ('date_created', 'created_by')
    search_fields = ('name',)