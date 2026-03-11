from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import MpesaAccount, BankAccount
from .serializers import MpesaAccountSerializer, BankAccountSerializer
from .services import add_mpesa_account, add_bank_account, set_primary_mpesa_account


class MpesaAccountListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/banking/mpesa/  — list all active M-Pesa accounts for current user
    POST /api/banking/mpesa/  — add a new M-Pesa account

    Note: is_primary is read-only. The service auto-sets primary
    on first account, or use /mpesa/<id>/set-primary/ to change it.
    """
    serializer_class   = MpesaAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MpesaAccount.objects.filter(
            user=self.request.user,
        ).order_by('-is_primary', '-created_at')

    def perform_create(self, serializer):
        # Pass validated_data to service, NOT directly to create()
        # so the service can strip is_primary and control auto-primary logic
        add_mpesa_account(self.request.user, serializer.validated_data.copy())


class MpesaAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/banking/mpesa/<id>/  — retrieve one account
    PATCH  /api/banking/mpesa/<id>/  — update account details
    DELETE /api/banking/mpesa/<id>/  — soft-delete account
    """
    serializer_class   = MpesaAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MpesaAccount.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        if account.is_primary:
            return Response(
                {'error': 'Cannot delete your primary M-Pesa account. Set another as primary first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Soft delete — never physically remove payment records
        account.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetPrimaryMpesaView(APIView):
    """
    POST /api/banking/mpesa/<id>/set-primary/
    Marks the given account as the primary receiving account.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            account = set_primary_mpesa_account(request.user, pk)
            return Response(MpesaAccountSerializer(account).data)
        except MpesaAccount.DoesNotExist:
            return Response(
                {'error': 'Account not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )


class BankAccountListCreateView(generics.ListCreateAPIView):
    serializer_class   = BankAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BankAccount.objects.filter(
            user=self.request.user,
        ).order_by('-is_primary', '-created_at')

    def perform_create(self, serializer):
        add_bank_account(self.request.user, serializer.validated_data.copy())


class BankAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class   = BankAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        if account.is_primary:
            return Response(
                {'error': 'Cannot delete your primary bank account. Set another as primary first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
