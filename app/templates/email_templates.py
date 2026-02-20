class EmailTemplates:
    @staticmethod
    def get_verification_email(
        user_name: str, verify_link: str, temp_password: str = None
    ) -> tuple[str, str]:
        subject = "Welcome to FastBank - Verify Your Account"

        content = f"""
        Hello {user_name},
        
        Welcome to FastBank! Your account has been created.
        """

        if temp_password:
            content += f"\n        Your temporary password is: {temp_password}\n"

        content += f"""
        Please verify your account by clicking the link below (valid for 15 minutes):
        {verify_link}
        
        If you did not request this, please ignore this email.
        """
        return subject, content

    @staticmethod
    def get_password_reset_email(reset_link: str) -> tuple[str, str]:
        subject = "FastBank - Password Reset Request"
        content = f"""
        Hello,
        
        We received a request to reset your password for your FastBank account.
        
        Please reset your password by clicking the link below (valid for 15 minutes):
        {reset_link}
        
        If you did not request a password reset, please ignore this email.
        Your password will remain unchanged.
        """
        return subject, content

    @staticmethod
    def get_verification_resend_email(verify_link: str) -> tuple[str, str]:
        subject = "FastBank - Verify Your Account"
        content = f"""
        Hello,
        
        You requested a new verification link for your FastBank account.
        
        Please verify your account by clicking the link below (valid for 15 minutes):
        {verify_link}
        
        If you did not request this, please ignore this email.
        """
        return subject, content

    @staticmethod
    def get_emi_failure_email(
        user_name: str,
        loan_amount: float,
        emi_amount: float,
        account_balance: float,
        due_date: str,
    ) -> tuple[str, str]:
        subject = "EMI Payment Failed - Insufficient Funds"
        shortfall = emi_amount - account_balance

        content = f"""
        Dear {user_name},

        We attempted to deduct your EMI payment of ₹{emi_amount:,.2f} on {due_date}, but the transaction could not be completed due to insufficient funds in your account.

        Loan Details:
        - Loan Amount: ₹{loan_amount:,.2f}
        - EMI Amount: ₹{emi_amount:,.2f}
        - Current Account Balance: ₹{account_balance:,.2f}
        - Required Amount: ₹{emi_amount:,.2f}
        - Shortfall: ₹{shortfall:,.2f}

        Please ensure sufficient funds are available in your account to avoid late payment charges and maintain your credit score.

        You can add funds to your account and the system will attempt the deduction again next month.

        If you have any questions, please contact our support team.

        Best regards,
        FastBank Team
        """.strip()
        return subject, content

    @staticmethod
    def get_advance_repayment_failure_email(
        user_name: str, payment_amount: float, account_balance: float
    ) -> tuple[str, str]:
        subject = "Advance Loan Repayment Failed - Insufficient Funds"
        shortfall = payment_amount - account_balance

        content = f"""
        Dear {user_name},

        Your advance loan repayment of ₹{payment_amount:,.2f} could not be processed due to insufficient funds.

        Current balance: ₹{account_balance:,.2f}
        Required amount: ₹{payment_amount:,.2f}
        Shortfall: ₹{shortfall:,.2f}

        Please ensure sufficient funds are available and try again.

        Best regards,
        FastBank Team
        """.strip()
        return subject, content
