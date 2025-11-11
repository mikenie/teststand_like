def test_add(a: int, b: int) -> int:
    """测试加法函数
    
    Args:
        a (int): 第一个加数
        b (int): 第二个加数
    
    Returns:
        int: 两数之和
    """
    sum = a+b 

    return sum 

def test_subtract(a: int, b: int) -> int:
    """测试减法函数
    
    Args:
        a (int): 被减数
        b (int): 减数
    
    Returns:
        int: 两数之差
    """
    sub = a-b
    return sub

def test_multiply(a: int, b: int) -> int:
    """测试乘法函数
    
    Args:
        a (int): 第一个因数
        b (int): 第二个因数
    
    Returns:
        int: 两数之积
    """
    mul = a * b
    return mul

def test_divide(a: int, b: int) -> int:
    """测试除法函数
    
    Args:
        a (int): 被除数
        b (int): 除数
    
    Returns:
        int: 两数之商
    """
    if b == 0:
        raise ValueError("除数不能为零")
    div = a / b
    return div
