from dateutil.relativedelta import relativedelta


def calculate_installment_dates(start_date, count, frequency):
    """
    Calculate installment dates based on start date, count, and frequency.
    
    Args:
        start_date (date): Starting date for installments
        count (int): Number of installments
        frequency (str): 'month', 'week', or 'day'
        
    Returns:
        list: List of dates for each installment
    """
    result = []
    current_date = start_date
    
    for i in range(count):
        result.append(current_date)
        if frequency == 'month':
            current_date = current_date + relativedelta(months=1)
        elif frequency == 'week':
            current_date = current_date + relativedelta(weeks=1)
        else:  # day
            current_date = current_date + relativedelta(days=1)
    
    return result


def calculate_equal_installments(total_amount, count, initial_amount=0, intermediate_amount=0, final_amount=0):
    """
    Calculate equal installment amounts.
    
    Args:
        total_amount (float): Total amount to distribute
        count (int): Number of installments
        initial_amount (float): Initial payment amount
        intermediate_amount (float): Intermediate payment amount
        final_amount (float): Final payment amount
        
    Returns:
        float: Amount per installment
    """
    remaining = total_amount - initial_amount - intermediate_amount - final_amount
    if remaining < 0:
        return 0
    
    if count <= 0:
        return 0
        
    return remaining / count


def split_equal_installments(total_amount, count, currency, initial_amount=0.0, intermediate_amount=0.0, final_amount=0.0):
    """
    Split remaining amount into "count" installments with proper currency rounding,
    adjusting the last installment to ensure the exact total is reached.

    Args:
        total_amount (float): Total to distribute (e.g., sale total)
        count (int): Number of installments
        currency (res.currency): Currency record to use for rounding
        initial_amount (float): Initial down payment (already rounded if needed)
        intermediate_amount (float): Intermediate payment (already rounded if needed)
        final_amount (float): Final payment (already rounded if needed)

    Returns:
        list[float]: List of installment amounts that sum exactly to total_amount - initial - intermediate - final
    """
    if count <= 0:
        return []

    remaining = (total_amount or 0.0) - (initial_amount or 0.0) - (intermediate_amount or 0.0) - (final_amount or 0.0)
    # If negative, return zeros to let caller validate/raise
    if remaining < 0:
        return [0.0] * count

    # Base per-installment amount (pre-rounding)
    base = remaining / count if count else 0.0
    # Round each installment using currency rules
    amounts = []
    for i in range(count - 1):
        amounts.append(currency.round(base))
    # Last installment takes the residual to ensure exact match
    residual = remaining - sum(amounts)
    amounts.append(currency.round(residual))

    # As a safety, if rounding produced a tiny mismatch, adjust the last value
    diff = currency.round(remaining - sum(amounts))
    if diff:
        amounts[-1] = currency.round(amounts[-1] + diff)

    return amounts
