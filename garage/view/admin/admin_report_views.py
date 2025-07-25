
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.views import View
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from garage.models import User, FinancialYear, SoftwareInfo
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from django.core.exceptions import ValidationError
from django.contrib import messages
import os
import re
from datetime import datetime

from garage.models import User, FinancialYear, SoftwareInfo, ClientGarage, ClientFiscalYear

@login_required
def admin_report_views(request):
    if request.user.is_superuser or request.user.role != 'admin':
        return redirect(f'/{request.user.role}/dashboard/')
    return render(request, 'admin/reports.html', {'user': request.user})