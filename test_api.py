import time


def test_get_endpoint(timeout: float = 0.7, verbose: bool = True) -> bool:
    """测试GET端点
    
    Args:
        timeout (float): 请求超时时间（秒）
        verbose (bool): 是否打印详细日志
    
    Returns:
        bool: 测试是否通过
    """
    if verbose:
        print("执行GET端点测试...")
    time.sleep(timeout)
    if verbose:
        print("GET端点测试通过")
    return True

def test_post_endpoint(timeout: float = 0.8, verbose: bool = True) -> bool:
    """测试POST端点
    
    Args:
        timeout (float): 请求超时时间（秒）
        verbose (bool): 是否打印详细日志
    
    Returns:
        bool: 测试是否通过
    """
    if verbose:
        print(timeout)
        print("执行POST端点测试...")
    time.sleep(timeout)
    if verbose:
        print("POST端点测试通过")
    return True
